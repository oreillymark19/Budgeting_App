import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import json
import os
from datetime import datetime
import plotly.express as px
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "config", "config.json"))
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "budget.db"))
BLACKLIST_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "config", "blacklist.json"))
MAPPING_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "config", "mapping.json"))
NO_AUTO_CLASSIFY_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "config", "no_auto_classify.json"))

# --- Load Configurations ---
def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

config = load_config()

st.set_page_config(page_title="Local Budget Tracker", layout="wide")

# --- Data & Logic Functions ---
def get_data(month_year=None):
    """Fetch transactions, optionally filtered by Month (YYYY-MM)."""
    if not os.path.exists(DB_PATH): return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as conn:
        query = "SELECT * FROM transactions"
        if month_year:
            query += f" WHERE Transaction_Date LIKE '{month_year}%'"
        df = pd.read_sql(query + " ORDER BY Transaction_Date DESC", conn)
    return df

def delete_transactions(ids_to_delete):
    """Removes from DB and adds to blacklist to prevent re-ingestion."""
    # 1. Update Blacklist
    blacklist = []
    if os.path.exists(BLACKLIST_PATH):
        with open(BLACKLIST_PATH, 'r') as f:
            blacklist = json.load(f)
    
    blacklist.extend(ids_to_delete)
    with open(BLACKLIST_PATH, 'w') as f:
        json.dump(list(set(blacklist)), f) # Ensure uniqueness

    # 2. Delete from DB
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"DELETE FROM transactions WHERE transaction_id IN ({','.join(['?']*len(ids_to_delete))})", ids_to_delete)
    st.success(f"Deleted {len(ids_to_delete)} transactions and added to blacklist.")

def apply_category_updates(changes_dict, original_df):
    """
    Processes the 'edited_rows' from st.data_editor.
    changes_dict format: {row_index: {'Category': 'NewValue'}}
    """
    with sqlite3.connect(DB_PATH) as conn:
        for row_idx, updates in changes_dict.items():
            if 'Category' in updates:
                new_cat = updates['Category']
                txn_id = original_df.iloc[row_idx]['transaction_id']
                description = original_df.iloc[row_idx]['Description']

                # 1. Update SQLite
                conn.execute(
                    "UPDATE transactions SET Category = ? WHERE transaction_id = ?", 
                    (new_cat, txn_id)
                )
                
                # 2. Update mapping.json (Autocomplete Memory)
                update_mapping_memory(description, new_cat)
    
    st.success("Database and Memory updated!")

def load_no_auto_classify():
    if not os.path.exists(NO_AUTO_CLASSIFY_PATH):
        return []
    with open(NO_AUTO_CLASSIFY_PATH, 'r') as f:
        return json.load(f)

def save_no_auto_classify(items):
    os.makedirs(os.path.dirname(NO_AUTO_CLASSIFY_PATH), exist_ok=True)
    with open(NO_AUTO_CLASSIFY_PATH, 'w') as f:
        json.dump(sorted(set(items)), f, indent=4)

def update_mapping_memory(description, category):
    vendor_key = description.strip().lower()

    # Skip memory-writes for vendors the user has opted out of auto-classification
    no_classify = load_no_auto_classify()
    if any(term in vendor_key for term in no_classify):
        return

    mapping = {}
    if os.path.exists(MAPPING_PATH):
        with open(MAPPING_PATH, 'r') as f:
            mapping = json.load(f)

    mapping[vendor_key] = category

    with open(MAPPING_PATH, 'w') as f:
        json.dump(mapping, f, indent=4)

# --- UI Layout ---
st.title("💰 Personal Budget Dashboard")

# Month Selector
df_all = get_data() # Get all to find available months
st.sidebar.title("Navigation")
page = st.sidebar.selectbox(
    "Go to", 
    ["📊 Monthly Analytics", "📅 Custom Date View", "🗂️ Transactions by Category", "❓ Uncategorized Transactions", "🚫 Vendor Rules", "⚙️ Manage Data", "📥 Upload Transactions"]
)

if not df_all.empty:
    df_all['Month_Year'] = pd.to_datetime(df_all['Transaction_Date']).dt.strftime('%Y-%m')
    available_months = sorted(df_all['Month_Year'].unique(), reverse=True)
    selected_month = st.selectbox("Select Month", available_months)
    df = df_all[df_all['Month_Year'] == selected_month]
else:
    st.sidebar.info("Upload data to see monthly metrics.")

# --- Sidebar Metrics ---
fixed_total = sum(config['fixed_costs'].values())

# Check if income from transactions exceeds config, if so use that as the income figure for better accuracy. Otherwise, fall back to config value.
if df[df['Category'] == 'Income']['Amount'].sum() > config['monthly_income']:
    income = df[df['Category'] == 'Income']['Amount'].sum()
else:
    income = config['monthly_income']

variable_spent = df.loc[(~df['Category'].isin(['Income', 'Investment', 'Housing'])) & df['Category'].notnull(), 'Amount'].mul(-1).sum()
total_out = fixed_total + variable_spent
remaining = income - total_out - config['savings_goal']

st.sidebar.header(f"Overview: {selected_month}")
st.sidebar.metric("Income", f"${income:,.2f}")
st.sidebar.metric("Savings Goal", f"${config['savings_goal']:,.2f}")
st.sidebar.metric("Safe to Spend", f"${remaining:,.2f}", 
                  delta="Over Budget" if remaining < 0 else "On Track",
                  delta_color="normal" if remaining >= 0 else "inverse")

# --- Tabs ---

if page == "📊 Monthly Analytics":
    st.subheader(f"Spending Summary: {selected_month}")

    spend_df = df[~df['Category'].isin(['Income', 'Investment', 'Housing']) & df['Category'].notnull()].copy()
    max_spend = income - config['savings_goal']

    if not spend_df.empty:
        spend_df['Transaction_Date'] = pd.to_datetime(spend_df['Transaction_Date'])
        spend_df['Day'] = spend_df['Transaction_Date'].dt.day

        daily_spending = spend_df.groupby('Day')['Amount'].sum().mul(-1)
        last_day = int(daily_spending.index.max())
        all_days = pd.Index(range(1, last_day + 1), name='Day')
        cumulative = daily_spending.reindex(all_days, fill_value=0).cumsum()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=cumulative.index,
            y=cumulative.values,
            mode='lines+markers',
            line=dict(shape='spline', color='#ff4b4b', width=3),
            name='Cumulative Spending',
            hovertemplate='Day %{x}<br>Cumulative: $%{y:,.2f}<extra></extra>'
        ))
        fig.add_hline(
            y=max_spend,
            line_dash='dash',
            line_color='#2ca02c',
            annotation_text=f"Max Spend: ${max_spend:,.2f}",
            annotation_position='top right'
        )
        fig.update_layout(
            title=f"Cumulative Variable Spending: {selected_month}",
            xaxis_title="Day of Month",
            yaxis_title="Total Spending ($)",
            xaxis=dict(dtick=1),
            yaxis=dict(tickprefix='$', tickformat=',.0f'),
            hovermode='x unified',
            margin=dict(l=20, r=20, t=50, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No variable spending recorded for this month yet.")

    st.write("### Income, Investment & Housing")
    if not df.empty:
        key_cats = ['Income', 'Investment', 'Housing']
        key_totals = (
            df[df['Category'].isin(key_cats)]
            .groupby('Category')['Amount']
            .sum()
            .abs()
            .reindex(key_cats, fill_value=0)
            .reset_index()
        )

        fig_key = px.bar(
            key_totals,
            x='Category',
            y='Amount',
            color='Category',
            text_auto='.2s',
            title=f"Totals for {selected_month}",
            labels={'Amount': 'Total ($)'},
            category_orders={'Category': key_cats}
        )
        fig_key.update_traces(
            hovertemplate="<b>%{x}</b><br>Total: $%{y:,.2f}<extra></extra>",
            marker_line_color='rgb(8,48,107)',
            marker_line_width=1.5,
            opacity=0.8
        )
        st.plotly_chart(fig_key, use_container_width=True)

    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.write("### Expenses by Category")
        if not df.empty:
            # Group data for the bar chart
            cat_totals = df[~df['Category'].isin(['Income','Investment','Housing'])].groupby('Category')['Amount'].sum().mul(-1).reset_index()
            cat_totals = cat_totals.sort_values(by='Amount', ascending=False)

            # Create an interactive bar chart
            fig_bar = px.bar(
                cat_totals, 
                x='Category', 
                y='Amount',
                color='Category',
                text_auto='.2s',
                title="Variable Spending by Category",
                labels={'Amount': 'Total Spent ($)'}
            )
            
            # Customizing hover behavior
            fig_bar.update_traces(
                hovertemplate="<b>%{x}</b><br>Total: $%{y:,.2f}<extra></extra>",
                marker_line_color='rgb(8,48,107)',
                marker_line_width=1.5, 
                opacity=0.8
            )
            
            st.plotly_chart(fig_bar, use_container_width=True)

    with col2:
        st.write("### Quick Breakdown")
        if not df.empty:
            # Display a clean summary table
            summary_table = df[~df['Category'].isin(['Income','Investment','Housing'])].groupby('Category')['Amount'].sum().sort_values(ascending=False)
            st.table(summary_table.map("${:,.2f}".format))
            
            # Show percentage of variable budget
            total_var = df[~df['Category'].isin(['Income','Investment','Housing'])]['Amount'].sum()
            st.info(f"Total Variable Spending: ${total_var:,.2f}")

elif page == "📅 Custom Date View":
    st.subheader("📅 Custom Date View")
    
    # Ensure date objects are handled correctly
    df_all['Transaction_Date'] = pd.to_datetime(df_all['Transaction_Date'])
    
    # Date Range Inputs
    col_start, col_end = st.columns(2)
    with col_start:
        start_date = st.date_input("Start Date", value=df_all['Transaction_Date'].min())
    with col_end:
        end_date = st.date_input("End Date", value=df_all['Transaction_Date'].max())

    if start_date <= end_date:
        # Filter data for this tab only
        mask = (df_all['Transaction_Date'].dt.date >= start_date) & (df_all['Transaction_Date'].dt.date <= end_date)
        range_df = df_all[mask].copy()

        if not range_df.empty:
            # Metrics for the range
            total_range_spent = range_df[~range_df['Category'].isin(['Income','Investment','Housing'])]['Amount'].sum() * -1
            days_in_range = (end_date - start_date).days + 1
            avg_daily = total_range_spent / days_in_range

            m1, m2, m3 = st.columns(3)
            m1.metric("Total Range Spending", f"${total_range_spent:,.2f}")
            m2.metric("Days in Range", f"{days_in_range}")
            m3.metric("Daily Average", f"${avg_daily:,.2f}")

            # Range Chart
            range_cat_totals = range_df[~range_df['Category'].isin(['Income','Investment','Housing'])].groupby('Category')['Amount'].sum().mul(-1).reset_index()
            range_cat_totals = range_cat_totals.sort_values(by='Amount', ascending=False)

            fig_range = px.bar(
                range_cat_totals, 
                x='Category', 
                y='Amount',
                color='Category',
                title=f"Spending from {start_date} to {end_date}",
                labels={'Amount': 'Total Spent ($)'},
                text_auto='.2f'
            )
            st.plotly_chart(fig_range, use_container_width=True)

            # Raw Data for the range
            with st.expander("View Transactions in this Range"):
                st.dataframe(range_df.drop(columns=['Month_Year']), use_container_width=True, hide_index=True)
        else:
            st.info("No transactions found for the selected range.")
    else:
        st.error("Error: Start Date must be before End Date.")

elif page == "🗂️ Transactions by Category":
    st.subheader(f"Categorized Spending for {selected_month}")
    st.caption("Edit the Category column to re-categorize a transaction. Changes update both the database and the auto-classify memory.")

    # Filter for only items that HAVE a category
    categorized_df = df[df['Category'].notna() & (df['Category'] != "")].reset_index(drop=True)

    if not categorized_df.empty:
        st.data_editor(
            categorized_df,
            use_container_width=True,
            column_config={
                "transaction_id": None,
                "Month_Year": None,
                "Category": st.column_config.SelectboxColumn("Category", options=config['categories']),
                "Amount": st.column_config.NumberColumn(format="$%.2f"),
                "Transaction_Date": "Date"
            },
            disabled=["transaction_id", "Description", "Amount", "Transaction_Date", "Account_Type"],
            hide_index=True,
            key="categorized_editor"
        )

        changes = st.session_state["categorized_editor"]["edited_rows"]
        if changes and st.button("Save Changes to Database"):
            apply_category_updates(changes, categorized_df)
            st.rerun()
    else:
        st.info("No transactions have been categorized for this month yet.")

elif page == "❓ Uncategorized Transactions":
    st.subheader("Speed Tagging")
    
    # Filter for uncategorized only
    mask = df['Category'].isna() | (df['Category'] == "")
    uncat_df = df[mask].copy()

    if not uncat_df.empty:
        # The 'key' is vital here to track state
        edited_df = st.data_editor(
            uncat_df,
            column_config={
                "Category": st.column_config.SelectboxColumn("Category", options=config['categories']),
                "transaction_id": None
            },
            disabled=["transaction_id", "Description", "Amount", "Transaction_Date"],
            key="cat_editor"
        )

        # Access the changes via st.session_state
        changes = st.session_state["cat_editor"]["edited_rows"]
        
        if changes and st.button("Save Changes to Database"):
            apply_category_updates(changes, uncat_df)
            st.rerun() # Refresh to move items out of 'Uncategorized'
    else:
        st.success("Everything is categorized!")

elif page == "🚫 Vendor Rules":
    st.subheader("🚫 Never Auto-Classify")
    st.caption(
        "Add description substrings (case-insensitive) that should stay uncategorized. "
        "Useful for stores like Walmart where the right category depends on what was bought. "
        "Existing transactions keep their current category — this only affects new imports and future edits."
    )

    no_classify = load_no_auto_classify()

    with st.form("add_no_classify_rule", clear_on_submit=True):
        new_term = st.text_input("Substring to block (e.g. 'walmart')")
        submitted = st.form_submit_button("Add Rule")
        if submitted:
            term = new_term.strip().lower()
            if not term:
                st.warning("Enter a non-empty substring.")
            elif term in no_classify:
                st.info(f"'{term}' is already on the list.")
            else:
                no_classify.append(term)
                save_no_auto_classify(no_classify)
                st.success(f"Added '{term}'.")
                st.rerun()

    st.write("### Current Rules")
    if no_classify:
        for term in sorted(no_classify):
            col1, col2 = st.columns([4, 1])
            col1.code(term, language=None)
            if col2.button("Remove", key=f"rm_{term}"):
                no_classify.remove(term)
                save_no_auto_classify(no_classify)
                st.rerun()
    else:
        st.info("No rules yet. Add one above to stop auto-classification for specific vendors.")

elif page == "⚙️ Manage Data":
    st.subheader("Delete Transactions")
    st.write("Select rows to permanently delete and blacklist.")
    to_delete_df = st.dataframe(
        df, 
        use_container_width=True, 
        on_select="rerun", 
        selection_mode="multi-row",
        column_config={"transaction_id": None}, # ID stays in the background
        hide_index=True
    )    

    selected_indices = to_delete_df.selection.rows
    if selected_indices:
        selected_ids = df.iloc[selected_indices]['transaction_id'].tolist()
        
        # Using a popover as a "safety catch"
        with st.popover(f"Confirm Deletion ({len(selected_ids)} items)"):
            st.warning("This will permanently delete these transactions and prevent them from being re-added.")
            if st.button("Confirm Permanent Delete"):
                delete_transactions(selected_ids)
                st.rerun()

elif page == "📥 Upload Transactions":
    st.subheader("📥 Upload & Sync Transactions")
    uploaded_files = st.file_uploader(
        "Drag and drop CSV files", 
        type="csv", 
        accept_multiple_files=True
    )

    if uploaded_files:
        if st.button("Process & Cleanup"):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            raw_dir = os.path.abspath(os.path.join(base_dir, "..", "data", "raw"))
            os.makedirs(raw_dir, exist_ok=True)
            
            # 1. Save to raw folder
            saved_paths = []
            for uploaded_file in uploaded_files:
                file_dest = os.path.join(raw_dir, uploaded_file.name)
                with open(file_dest, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                saved_paths.append(file_dest)
            
            st.info(f"Buffered {len(saved_paths)} files to {raw_dir}")

            # 2. Run the cleaning script
            try:
                # Runs process_and_save() logic from cleaning.py
                script_path = os.path.join(base_dir, "cleaning.py")
                result = subprocess.run(
                    ["python", "-u", script_path], # -u for unbuffered output
                    capture_output=True, 
                    text=True
                )
                
                if result.returncode == 0:
                    st.success("✅ Sync Successful: Database Updated.")
                    st.write("### Sync Output:")
                    st.code(result.stdout) # This will show you the logger.info messages
                    if "Successfully synced 0 new transactions" in result.stdout:
                        st.warning("The script ran, but identified all transactions as duplicates or blacklisted.")
                    
                    # 3. Auto-Cleanup: Remove files after processing
                    for path in saved_paths:
                        if os.path.exists(path):
                            os.remove(path)
                    st.toast("Temporary CSV files deleted from raw folder.")
                    
                    st.rerun() # Refresh UI with new data
                else:
                    st.error(f"Sync Failed: {result.stderr}")
            except Exception as e:
                st.error(f"Automation Error: {e}")
    