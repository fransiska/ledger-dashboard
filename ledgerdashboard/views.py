import datetime
from dateutil.relativedelta import *
from ledgerdashboard import app
from ledgerdashboard.ledger import ledger
from ledgerdashboard.renderer import LayoutRenderer
from ledgerdashboard.layout import Dashboard, Expenses
from ledgerdashboard import settings
import ledgerdashboard.settings as s
from flask import flash, request
from pprint import pprint

months = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]

renderer = LayoutRenderer()
app.secret_key = settings.SECRET_KEY

l = ledger.Ledger.new(filename=settings.LEDGER_FILE)
ledger_writer = ledger.LedgerWriter(settings.LEDGER_FILE)


@app.route("/<int:year>/<int:month>")
def index_date(year,month,*args):
    return index(datetime.date(year+1 if month == 12 else year, 1 if month == 12 else month+1, 1) - datetime.timedelta(days=1))

@app.route("/")
def index(date = None):
    layout = Dashboard()
    layout.current_date = date if date else datetime.date.today()
    layout.current_datetime = datetime.datetime.combine(layout.current_date, datetime.datetime.max.time())
    next_month = layout.current_datetime + relativedelta(months=1)

    layout.accounts = [
        {"name": format_account(account), 'balance': format_amount(balance,10)}
        for account, cur, balance in l.balance(accounts=s.Accounts.ASSETS_PATTERN, limit="date < [{}]".format(next_month.strftime("%B %Y")))
    ]

    layout.debts = [
        {"name": format_account(account), 'balance': format_amount(float(balance) * -1,10)}
        for account, cur, balance in l.balance(accounts=s.Accounts.LIABILITIES_PATTERN, limit="date < [{}]".format(next_month.strftime("%B %Y")))
    ]

    layout.budget_balances = [
        {
            "name": format_account(account),
            'balance': format_amount(balance),
            "first": account == s.Accounts.BUDGET_PATTERN
        }
        for account, cur, balance
        in l.balance(accounts=s.Accounts.BUDGET_PATTERN, limit="date >= [{}] and date < [{}]".format(layout.current_date.strftime("%B %Y"),next_month.strftime("%B %Y")))
    ]

    layout.expense_balances = [
        {
            "name": format_account(account),
            'balance': format_amount(balance,9),
            "first": account == s.Accounts.EXPENSES_PATTERN
        }
        for account, cur, balance
        in l.balance(accounts=s.Accounts.EXPENSES_PATTERN, limit="date >= [{}] and date < [{}]".format(layout.current_date.strftime("%B %Y"),next_month.strftime("%B %Y")))
    ]

    layout.income = [
        {
            "name": format_account(account),
            'balance': format_amount(balance,9),
            "first": account == s.Accounts.INCOME_PATTERN
        }
        for account, cur, balance
        in l.balance(accounts=s.Accounts.INCOME_PATTERN, limit="date >= [{}] and date < [{}]".format(layout.current_date.strftime("%B %Y"),next_month.strftime("%B %Y")))
    ]

    layout.last_expenses = [
        {'payee': txn['payee'], 'note': txn['note'], 'amount': format_amount(txn['amount'])}
        for txn
        in l.register(accounts=s.Accounts.EXPENSES_PATTERN, limit="date >= [{}] and date < [{}]".format(layout.current_date.strftime("%B %Y"),next_month.strftime("%B %Y")))[:-15:-1]
    ]

    layout.unbudgeted = [
        {'payee': txn['payee'], 'note': txn['note'], 'amount': format_amount(txn['amount'])}
        for txn
        in l.register(accounts=s.Accounts.UNBUDGETED_PATTERN, limit="date >= [{}] and date < [{}]".format(layout.current_date.strftime("%B %Y"),next_month.strftime("%B %Y")))[:-15:-1]
    ]

    current_month = layout.current_date.month

    # Date
    reg = [txn['date'] for txn in l.register(accounts="")]
    layout.starting_date = reg[0][:5]
    layout.ending_date = reg[-1]
    layout.month_range = []
    for year in range(int(layout.starting_date[:4]),int(layout.ending_date[:4])+1):
        layout.month_range.extend([{"month":"{}/{}".format(year,i)} for i in range(1,13)])

    flow = []
    net_worth = []

    for i in range(-3,1,1):
        start_month = layout.current_datetime + relativedelta(months=i)
        end_month = layout.current_datetime + relativedelta(months=i+1)
        start_month_nr = start_month.month-1
        start_year = start_month.year
        end_month_nr = end_month.month-1
        end_year = end_month.year

        result = [
            {
                "name": format_account(account),
                'balance': format_amount(balance,9),
                "first": account == s.Accounts.INCOME_PATTERN
            }
            for account, cur, balance
            in l.balance(accounts=" ".join([s.Accounts.LIABILITIES_PATTERN, s.Accounts.ASSETS_PATTERN,"-n"]), limit="date < [{} {}]".format(months[end_month_nr], end_year))
        ]

        amount = sum([int(res["balance"].split()[1].replace(",","")) for res in result])
        net_worth.append({
            'month': months[start_month_nr],
            'amount': format_amount(amount),
            'type': "negative" if amount < 0 else "positive"
        })

        result = l.register(
            accounts=" ".join([s.Accounts.EXPENSES_PATTERN, s.Accounts.INCOME_PATTERN]),
            M=True, collapse=True,
            limit="date >= [{} {}] and date < [{} {}]".format(
                months[start_month_nr], start_year,
                months[end_month_nr], end_year)
        )

        amount = float(result[0]['amount']) * -1 if len(result) > 0 else 0
        flow.append({
            'month': months[start_month_nr],
            'amount': format_amount(amount),
            'type': "negative" if amount < 0 else "positive"
        })

    layout.cash_flow = flow
    layout.net_worth = net_worth

    return renderer.render(layout)


@app.route("/expenses", methods=['GET'])
def expenses_get():
    return renderer.render(Expenses())


@app.route("/expenses", methods=['POST'])
def expenses_post():
    for field in ['payee', 'account', 'amount']:
        if field not in request.form or not request.form.get(field):
            flash("Field {} not set".format(field), 'error')
            return renderer.render(Expenses(request.form))

    posting = {
        "date": request.form.get('date'),
        "payee": request.form.get('payee', ""),
        "account": request.form.get('account', ""),
        "use_source": request.form.get('use_source', "") == "on",
        "source_account": request.form.get('source_account', ""),
        "amount": request.form.get('amount', 0),
        "description": request.form.get('description', "")
    }

    ledger_writer.write_expense(posting)

    flash("Expense successfully added")
    return "See other", 303, {"Location": "/expenses"}


@app.route("/api/accounts/")
@app.route("/api/accounts/<account_filter>")
def api_accounts(account_filter=""):
    import json
    term = request.args.get("term", "")
    accounts = json.dumps([
        l.make_aliased(account)
        for account in l.accounts(account_filter)
        if term.lower() in account.lower()
    ])
    return accounts, 200, {"Content-Type": "application/json"}


@app.route("/api/payee/")
def api_payee():
    import json
    term = request.args.get("term", "")
    payees = {txn['payee'] for txn in l.register() if term.lower() in txn['payee'].lower()}
    return json.dumps(sorted(payees)), 200, {"Content-Type": "application/json"}


def format_amount(amount, width=6):
    return ("JPY {: >"+str(width)+"}").format("{:,.0f}".format(float(amount)))
    #return ("JPY {:,>}".format(float(amount)))


def format_account(account):
    if ":" not in account:
        return account

    return ("&nbsp;" * 4) + ":".join(account.split(":")[1:])


def days_until_next_transaction(txn_date: datetime.date, current_datetime):
    """
    Calculates the number of days until the next transaction (occurring next month)
    :param txn_date: datetime.date
    :return: int
    """

    return (txn_date + relativedelta(months=1) - current_datetime).days


def get_unmatched_txns(haystack, needles):
    """
    Tries to find the transactions in needles that don't occur in the haystack
    :param haystack:list[dict]
    :param needles:list[dict]
    :return:
    """
    unmatched_txns = []

    for txn in haystack:
        found = False
        for txn_tm in needles:
            if txn['payee'] == txn_tm['payee'] and txn['amount'] == txn_tm['amount']:
                found = True
                break
        if not found:
            unmatched_txns.append(txn)

    return unmatched_txns
