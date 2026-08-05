Let's start brainstorming some requirements (and starting to fill in the technical charter where requirements impact that, although we'll dedicate a whole task to that for the most important details).

With this project, we'll be replacing my personal finance Excel spreadsheet with a Textual UI written in Python. Since it's not a web app, our Layer 2 documentation will be operations in general instead of a formal web service API.

The project will be split into three modules:
- Balance sheet
- Goals
- Cash flow and expenses

I don't track each expense. I track the current state of my accounts and make sure the amount I'm retaining each month largely matches what I have entered in my cash flow. At the end of each month, I take a snapshot of my current net worth to assess this.

## Balance Sheet
### Assets
- Current accounts (chequing, savings, WISE)
- Receivables (expense reports from work, manual insurance claims)
- Investment accounts:
  - Type: RRSP, TFSA, RESP, LIRA, DCPP, Unregistered
  - Holdings: Cash, equities, ETFs, mutual funds, GICs
- House
- Cars

### Liabilities
- Credit cards
- Mortgage
- HELOC
- Home sale fees (7% of the home's value so we don't get too comfortable with how much equity there is there)

### Notes

Ownership of each account can be Husband, Wife or Joint. Let's assume that the list of owners is configurable.

The value of investment accounts should be calculatable by its holdings.

## Goals
Goals are essentially buckets. Goals can claim a portion of the assets registered above. Usually current assets (bank accounts) are grouped together for this claim; i.e., it doesn't matter if it's in the chequing or savings account. Technically, each holding in an investment can be assigned to different goals, but that doesn't happen often. That's something we may capture in the database so it's forward-compatible, but simplify in the UI to start.

Some example goals: emergency fund, vacation fund, primary and secondary automobile replenishment fund, retirement, children's post-secondary

### Cash flow and expenses
This part is completely separate from the other two. Here, for each person captured (Husband and Wife), we gather:

Salary Gross pay
 -> Less group retirement RRSP contribution
 -> Less taxes and deductions
 --> Salary net pay
Matched retirement contributions

Bonus Gross pay
 -> Less taxes and deductions
 --> Bonus net pay

We then capture our expected monthly expenses in a separate interface in order to arrive at an average monthly expense total. Each expense can be classified as coming from current assets or a credit card, and can be classified as regular or irregular; these are used for reporting/planning purposes only at the moment.

These are then all tied together in the final cash flow:

-> Net monthly salary from Husband and Wife
--> Less monthly expenses
--> Less automated retirement contributions
--> Less automated auto replacement contributions
--> Less automated post-secondary REST contributions
-> Monthly retained
--> x12 = Annual retained
--> Plus bonuses
-> Gross annual retained
--> Less large scale expenses (household improvements, major electronics and appliance)
-> Net annual retained
--> Plus all salary automated contributions and matchings (from the income configuration)
-> Total saved

The list of automated contributions should be configurable.

---

Below I've included some general clean-up instructions. Please apply these updates. **Do not run any git commit commands as a part of this or any work!**

## General Clean-up
- Please eliminate any mention of user management, particularly in functional requirement preconditions. Assume this will be a single-user system. No passphrase necessary. No encryption of the database is required.
- Auditability is not required at this time, but the architecture selected should leave it open to add it in the future.
- No import, export or backup features are required. Assume we'll take care of backing up the underlying SQL database independently of this work.
- Assume everything is in CAD. No other currencies required.
- Assume the Person table will be prepopulated with Husband, Wife, and Joint. The UI doesn't need to manage this.
- I removed the `rest-api.md` since it doesn't really make sense for this TUI app. Instead assume we'll use a plain-old three layer architecture: domain, services and user interface (Textual). Each layer only communicates directly with its adjacent tier. So our `02-operations` becomes a `service-operations.md` describing the "transaction scripts" that will fulfill the UI operations. **Do not fill this in now**. We're going to flesh out the data and UI flows first. Please update the charter with this, though (the application should be clearly structured in these layers).
- While we're updating the charter, please add note that the domain model will be authored with SQLAlchemy-first and the SQL schema will be generated from this model.

---

Next, let's work through this batch of updates and scope refinements.

## Data model
- Balance sheet must be broken down between current and long-term for assets and liabilities. There should be a current net worth and overall net worth provided.
- Each account should be able to be flagged as either: Current (Bank), Current (Other), or Long-term. Each liability can be either Current or Long-term. This is independent from the investment type field (RRSP, TFSA, RESP, etc.).
- Regarding the "snapshot" of our balance sheet that we take at the end of each month: The key number there to track is the "amount left to invest." That is the sum of all "Current (bank)" accounts, less current liabilities, less any Goals currently claiming funds in the "Current (bank)" accounts, less a $2,000 cushion (application configuration). The snapshot taking needs to be triggered by a user -- it's not an automatic operation. This is the value that should increase in lock-step with the retained amount from the Cash Flow module of the application.

## Investment Management
- Investment holdings require a fund name and should optionally be able to specify a symbol and unit quantity
- Holding values can either be scalar totals ($ value entered directly), or they can be calculated using the quantity by the last price of the entered symbol.
- Assume all investment account supports a single Cash value as well
- Each holding should be able to have a percentage classification into: Equity (Canada), Equity (US), Equity (Europe), Equity (APAC), Equity (Emerging), Fixed Income, Cash, Other. Assume this will be provided by an API that we will select later. These categories may be adjusted to reflect what's possible from publicly available APIs.
- We will have a brainstorming session to pick out publicly available APIs for all those data points mentioned above. The symbol storage for holdings will follow the symbology of whatever API product we choose.

## Goals
- Each goal can have a target dollar amount. This can be entered as either a scalar value for simple goals (e.g., an emergency fund), or a target amount. E.g., target $20,000 in January 2035 assuming an interest rate of 5%/a compounded monthly. Always assume monthly compounding for a target amount -- we'll never use this feature for any other period.
- Each goal can optionally have classification goals that we can track against. For simplicity, let's assume these can be hard-coded in the code and we'll just have a dropdown to choose which one to apply.

---

## Functional Requirements
- "including optionally setting an asset allocation breakdown": A breakdown isn't set on a holding. It'll be retrieved from an Asset Allocation API using the symbol provided. If the holding has a manually set price, then this breakdown will need to be manually entered. GICs will be manually entered as 100% Fixed Income, for example (the Cash line in an investment account is obviously 100% cash).
- We should add a requirement to explicitly capture "Searching for a security". We shouldn't just take the user's word that the entered security ticker is what the API is using. A quick typeahead search will come in handy here.

## Data Requirements
- Let's rename the account `type` Enum so that they're `asset_*` and `liability_*`
- Let's update `current_asset` to `asset_bank_account`
- Then we can simplify `term_classification` to just `current` and `long_term` and share that Enum between assets and liabilities
- Note that the previous change will impact the calculation of "Amount left to invest"
- Please update the fields to indicate which ones are fully derived and likely won't need to be persisted
- Please break out asset allocation categories into their own entity so that can be configurable and joinable in the resulting database
- The Goal classification is incorrect: the idea is that the classification goal is across _all_ categories. E.g., 20% Fixed Income, 10% Equity (Canada), etc. This mostly applies to the retirement goal/bucket.

---

Let's update the technical charter (@/specs/canonical/technical-charter.md ) next. As mentioned, we're developing Python TUI application using a standard three-layer model: domain, services and UI. Also, as subdivisions, please also keep the `balance_sheet`, `goals` and `cash_flow` as independent as possible with clear interfaces between them where they do interact.

We will use SQLAlchemy as our ORM. Our implementation will be domain model-first with the SQL database generated from there. Assume that through development, we'll just blow away our database and recreate from scratch whenever there's a change -- no need to track deltas until we go to prod. We will need to seed configuration data and mock data separately. We should assume that'll be done within a Python script to keep the flow consistent with this being Python-first. 

We should use Rich Domain Models whenever the logic is specific to rules of the domain. Anything specific to a particular UI flow should obviously go into the services layer. If there's any ambiguity, then please ask the user. 

Derived fields should not be persisted unless there is a performance reason to do so (the prompter will specifically ask for this; however, the LLM is free to make recommendations). 

All domain models and services require 80%+ unit test coverage. We should confirm this before closing each vertical slice. User interface logic does not require the same level of testing, but a reasonable baseline should be established. 

Also assume that each vertical slice should be linted before closing it too.

Some of these will affect our non-functionals too (@/specs/canonical/01-requirements/non-functional-requirements.md ) so please also keep those up-to-date.

---

I have put together a domain model in @/specs/canonical/01-requirements/domain-model.svg . This refines a lot of the ideas in the spec-driven repository. Could you please specifically look at updating @/specs/canonical/01-requirements/functional-requirements.md  and @/specs/canonical/01-requirements/data-requirements.md  based on these updates.

One large update is that the interface will open by asking for the current effective date for all reporting and data entry operations. This will affect both the Balance Sheet and Cash Flow modules. It will not affect the Goals (alll data points there are simple scalars).

---

I assume Yahoo! Finance allows us to query daily close values for the symbols we're looking up in `ListedSecurityHolding`s? I removed the `marketValue` from @/specs/canonical/01-requirements/domain-model.svg already based on this (let me know if I'm wrong).

Can you please update @/specs/canonical/01-requirements/functional-requirements.md  and @/specs/canonical/01-requirements/data-requirements.md  so that instead of writing `marketValue`, we say that we'll contact the API? 

We'll use the end of day value for previous days and the most recent quote if the active date is today.