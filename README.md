# 💰 Personal Budget Dashboard

A powerful, interactive personal budget tracking application built with Streamlit. Manage multiple bank accounts, analyze spending patterns, and maintain control over your finances with an intuitive web-based dashboard.

## Features

- **Multi-Bank Support**: Import transactions from multiple banks (RBC, Tangerine, and more)
- **Smart Transaction Management**: Automatically categorize transactions and edit categories on-the-fly
- **Data Persistence**: Store all transactions in a local SQLite database
- **Intelligent Duplicate Prevention**: Blacklist system prevents duplicate transaction ingestion
- **Interactive Analytics Dashboard**: 
  - Monthly spending overview with gauge visualizations
  - Spending breakdown by category
  - Custom date range analysis
  - Income vs. expense tracking
- **Budget Monitoring**: Real-time comparison against savings goals and monthly budget limits
- **Uncategorized Transaction Tracking**: Quickly identify and categorize transactions without category assignments
- **Data Management Interface**: Upload, delete, and manage transaction data with ease
- **Mapping Memory**: Automatic learning of vendor-to-category associations for faster categorization

## Tech Stack

- **Frontend**: [Streamlit](https://streamlit.io/) - Interactive web app framework
- **Backend**: Python 3.x
- **Database**: SQLite
- **Data Processing**: [Pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/)
- **Visualization**: [Plotly](https://plotly.com/), [Altair](https://altair-viz.github.io/)
- **Data Formats**: JSON for configuration files

## Installation

### Prerequisites
- Python 3.8 or higher
- Virtual environment (recommended)

### Setup

1. **Clone the repository** (or download the project files)
   ```bash
   git clone <repository-url>
   cd Budgeting_App
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv budget_app
   ```

3. **Activate the virtual environment**
   - On Windows (PowerShell):
     ```bash
     .\budget_app\Scripts\Activate.ps1
     ```
   - On Windows (Command Prompt):
     ```bash
     budget_app\Scripts\activate.bat
     ```
   - On macOS/Linux:
     ```bash
     source budget_app/bin/activate
     ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### Config Files

All configuration is managed through JSON files in the `config/` directory:

#### `config.json`
Main configuration file for budget parameters:
```json
{
    "monthly_income": ,
    "savings_goal": ,
    "fixed_costs": {
        "Contribution": 
    },
    "categories": [
        "Alcohol/Bars", "Baby", "Charity", "Gas", "Gifts", 
        "Housing", "Groceries", "Restaurants", "Uber", 
        "Entertainment", "Shopping", "Health", "Misc", 
        "Subscriptions", "Presto", "Income", "Investment"
    ]
}
```

**Key Parameters:**
- `monthly_income`: Your expected monthly income (in dollars)
- `savings_goal`: Target amount to save each month
- `fixed_costs`: Fixed monthly expenses (e.g., rent, utilities)
- `categories`: Available transaction categories for organization

#### `mapping.json`
Auto-generated file that stores vendor-to-category associations for intelligent autocomplete:
```json
{
    "amazon": "Shopping",
    "starbucks": "Restaurants",
    "uber": "Uber"
}
```
This file is automatically updated as you categorize transactions.

#### `blacklist.json`
Tracks transaction IDs that have been deleted to prevent re-ingestion:
```json
[
    "transaction_id_1",
    "transaction_id_2"
]
```

## Usage

### Running the Application

```bash
streamlit run src/app.py
```

The application will open at `http://localhost:8501` in your default web browser.

### Main Features

#### 📊 Monthly Analytics
View your spending overview for a selected month with:
- Total spending gauge against income
- Breakdown between fixed and variable costs
- Savings goal tracking
- Category-wise spending pie charts

#### 📅 Custom Date View
Analyze transactions across custom date ranges with flexible filtering options.

#### 🗂️ Transactions by Category
Browse and analyze transactions grouped by spending category.

#### ❓ Uncategorized Transactions
Quickly identify and categorize transactions that haven't been assigned a category yet.

#### ⚙️ Manage Data
- View all transactions in an editable table
- Update categories directly from the table
- Delete erroneous transactions
- Audit transaction history

#### 📥 Upload Transactions
Import new transaction CSVs from your banks with automatic duplicate detection and deduplication.

## Project Structure

```
Budgeting_App/
├── src/
│   ├── app.py              # Main Streamlit application
│   └── cleaning.py         # Data processing and ETL functions
├── config/
│   ├── config.json         # Budget configuration
│   ├── mapping.json        # Vendor-to-category mappings
│   └── blacklist.json      # Deleted transaction IDs
├── data/
│   ├── raw/                # CSV files from banks
│   │   ├── {bank_1}_*.csv
│   │   └── {bank_2}_*.csv
│   └── budget.db           # SQLite database (auto-created)
├── logs/                   # Application logs
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## Data Flow

1. **Import**: Bank transactions are imported from CSV files in `data/raw/`
2. **Clean**: Data is cleaned and standardized by `cleaning.py`
3. **Deduplicate**: Transactions are checked against the blacklist and database
4. **Store**: Valid transactions are stored in `data/budget.db`
5. **Categorize**: Automatic categorization using mapping rules
6. **Analyze**: Interactive dashboard visualizes spending patterns

## Database Schema

### transactions table
```
- transaction_id (PRIMARY KEY, UNIQUE)
- Date (Transaction date in YYYY-MM-DD format)
- Description (Merchant/transaction description)
- Amount (Transaction amount)
- Category (Assigned spending category)
- Bank (Source bank account)
```

## Logging

Application logs are stored in the `logs/` directory with monthly files:
- Format: `budget_sync_YYYY-MM.log`
- Includes both file and console output
- Useful for debugging data import issues

## Tips for Best Results

1. **Regular Updates**: Import transactions regularly to keep your budget current
2. **Consistent Categorization**: The mapping memory learns from your choices—be consistent for better auto-categorization
3. **Review Uncategorized**: Regularly check the uncategorized transactions view to catch and categorize new vendors
4. **Configuration Tuning**: Adjust `config.json` to match your actual income and expenses for accurate budget tracking
5. **Backup Data**: Periodically back up your `data/budget.db` file

## Supported Banks

Currently supports transaction imports from:
- RBC (Royal Bank of Canada)
- Tangerine

Additional banks can be added by extending the CSV parsing logic in `cleaning.py`.

## Troubleshooting

### No data showing in dashboard
- Ensure CSV files are placed in `data/raw/` directory
- Run the upload process from the "📥 Upload Transactions" page
- Check logs in `logs/` directory for import errors

### Duplicate transactions appearing
- Use the "⚙️ Manage Data" page to delete duplicates
- Deleted transactions are automatically blacklisted to prevent re-import

### Categories not updating
- Ensure you're using the correct category names from `config.json`
- Try refreshing the page after making changes

## Future Enhancements

Potential improvements for future versions:
- [ ] Budget alerts and notifications
- [ ] Multi-user support
- [ ] Recurring transaction detection
- [ ] Advanced forecasting and trend analysis
- [ ] Export reports (PDF, Excel)
- [ ] Mobile-friendly interface
- [ ] Cloud database integration
- [ ] Automated transaction import via bank APIs

## Contributing

Contributions are welcome! Please feel free to:
- Report bugs or issues
- Suggest new features
- Improve documentation
- Submit pull requests

## License

This project is provided as-is for personal use.

## Support

For issues or questions, please check the logs directory for debugging information or review the configuration files to ensure they're set up correctly.

---

**Happy budgeting! 💸**
