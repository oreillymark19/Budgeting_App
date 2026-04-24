import pandas as pd
import glob
import sqlite3
import hashlib
import logging
import os
from datetime import datetime
from typing import List
import json

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "raw"))
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "budget.db"))
MAPPING_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "config", "mapping.json"))
BLACKLIST_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "config", "blacklist.json"))
NO_AUTO_CLASSIFY_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "config", "no_auto_classify.json"))
LOG_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "logs"))
LOG_FILE = os.path.join(LOG_DIR, f"budget_sync_{datetime.now().strftime('%Y-%m')}.log")

# Ensure directories exist before starting
os.makedirs(LOG_DIR, exist_ok=True)

# --- Logging Setup (File + Console) ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create formatters
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_formatter = logging.Formatter('%(levelname)s: %(message)s')

# File Handler (Appends to the current month's log file)
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(file_formatter)
file_handler.setLevel(logging.INFO)

# Console Handler (For immediate feedback in your terminal)
console_handler = logging.StreamHandler()
console_handler.setFormatter(console_formatter)
console_handler.setLevel(logging.INFO)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# --- Functions (Logic remains consistent with your previous version) ---

def get_currency_rate(source: str, target: str, txn_date: datetime) -> float:
    try:
        from forex_python.converter import CurrencyRates
        return CurrencyRates().get_rate(source, target, txn_date)
    except Exception as e:
        logger.warning(f"Currency API failed for {txn_date.date()}: {e}. Using fallback 1.35.")
        return 1.35

def clean_rbc(files: List[str]) -> pd.DataFrame:
    if not files:
        logger.info("No RBC files found in raw directory.")
        return pd.DataFrame()

    try:
        df = pd.concat([pd.read_csv(f, index_col=False) for f in files], ignore_index=True)
        df['Transaction Date'] = pd.to_datetime(df['Transaction Date'], format='%m/%d/%Y')

        usd_mask = df['CAD$'].isna() & df['USD$'].notna()
        if usd_mask.any():
            logger.info(f"Converting {usd_mask.sum()} USD transactions to CAD.")
            df.loc[usd_mask, 'CAD$'] = df[usd_mask].apply(
                lambda x: x['USD$'] * get_currency_rate('USD', 'CAD', x['Transaction Date']), axis=1
            )

        cleaned = (
            df.assign(
                Description=(df['Description 1'].fillna('') + ' - ' + df['Description 2'].fillna('')).str.strip(),
                Amount=df['CAD$']
            )
            .rename(columns={'Account Type': 'Account_Type', 'Transaction Date': 'Transaction_Date'})
            .loc[:, ['Account_Type', 'Transaction_Date', 'Description', 'Amount']]
        )
        
        # Consistent spending orientation
        #cleaned.loc[cleaned['Account_Type'] == 'Visa', 'Amount'] *= -1
        return cleaned
    except Exception as e:
        logger.error(f"Critical error processing RBC: {e}")
        return pd.DataFrame()

def clean_tangerine(files: List[str]) -> pd.DataFrame:
    if not files:
        logger.info("No Tangerine files found in raw directory.")
        return pd.DataFrame()

    try:
        df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
        return (
            df.rename(columns={'Transaction date': 'Transaction_Date', 'Name': 'Description'})
            .assign(
                Transaction_Date=lambda x: pd.to_datetime(x['Transaction_Date'], format='%m/%d/%Y'),
                Account_Type='Mastercard'
            )
            .query("Description != 'PAYMENT - THANK YOU'")
            .loc[:, ['Account_Type', 'Transaction_Date', 'Description', 'Amount']]
        )
    except Exception as e:
        logger.error(f"Critical error processing Tangerine: {e}")
        return pd.DataFrame()

def generate_hashes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    def create_hash(row):
        # Precise formatting to prevent hash drift
        payload = f"{row['Transaction_Date']}|{str(row['Description']).lower()}|{row['Amount']:.2f}"
        return hashlib.sha256(payload.encode()).hexdigest()
    df['transaction_id'] = df.apply(create_hash, axis=1)
    return df

def load_no_auto_classify() -> List[str]:
    """Substrings that should never trigger auto-classification."""
    if not os.path.exists(NO_AUTO_CLASSIFY_PATH):
        return []
    with open(NO_AUTO_CLASSIFY_PATH, 'r') as f:
        return json.load(f)

def apply_mappings(df: pd.DataFrame) -> pd.DataFrame:
    """Checks for known vendor substrings in mapping.json and assigns categories."""
    if not os.path.exists(MAPPING_PATH) or df.empty:
        return df

    with open(MAPPING_PATH, 'r') as f:
        mapping = json.load(f)

    no_classify = load_no_auto_classify()

    def find_match(description):
        desc_lower = str(description).lower()
        # Hands off if the vendor is on the no-auto-classify list
        if any(term in desc_lower for term in no_classify):
            return None
        for vendor_key, category in mapping.items():
            # Matches if your mapping key (e.g., 'uber') is in the description
            if vendor_key in desc_lower:
                return category
        return None

    # Only apply to rows that don't already have a category assigned
    df['Category'] = df['Description'].apply(find_match)
    return df

def process_and_save():
    logger.info("--- Starting Budget Sync ---")
    
    rbc_list = glob.glob(os.path.join(DATA_DIR, "rbc*.csv"))
    tangerine_list = glob.glob(os.path.join(DATA_DIR, "tangerine*.csv"))

    df_rbc = clean_rbc(rbc_list)
    df_tang = clean_tangerine(tangerine_list)
    
    full_df = pd.concat([df_rbc, df_tang], ignore_index=True)
    if full_df.empty:
        logger.warning("Aborting: No data processed from input files.")
        return

    full_df = apply_mappings(full_df)

    # Handle duplicates by adding a small increment to the amount (if needed) before hashing
    is_duplicate = full_df.duplicated(subset=['Description', 'Amount', 'Transaction_Date'], keep='first')
    full_df.loc[is_duplicate, 'Amount'] += 0.01

    full_df = generate_hashes(full_df)

    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Ensure table structure exists
            conn.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    Account_Type TEXT,
                    Transaction_Date TEXT,
                    Description TEXT,
                    Amount REAL,
                    Category TEXT
                )
            ''')
            
            existing_ids = pd.read_sql("SELECT transaction_id FROM transactions", conn)['transaction_id'].values
            new_data = full_df[~full_df['transaction_id'].isin(existing_ids)]

            # In cleaning.py inside process_and_save():
            if os.path.exists(BLACKLIST_PATH):
                with open(BLACKLIST_PATH, 'r') as f:
                    blacklist = json.load(f)
                # Filter out anything in the blacklist
                new_data = new_data[~new_data['transaction_id'].isin(blacklist)]

            if not new_data.empty:
                new_data.to_sql("transactions", conn, if_exists="append", index=False)
                logger.info(f"Successfully synced {len(new_data)} new transactions to database.")
            else:
                logger.info("Sync complete. No new unique transactions found.")

    except Exception as e:
        logger.error(f"Database ingestion failed: {e}")
    
    logger.info("--- Sync Session Finished ---")

if __name__ == "__main__":
    process_and_save()