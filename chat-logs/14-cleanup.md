/start-slice @specs/work-product/slice-logs/2026-06-09-cash-flow.md refinements-and-fixes

We are now feature complete 🎉 We are starting a new vertical slice just to track the incremental improvements that remain.

Let's start with the Expenses panel of the Cash Flow module: the summary table should be fixed to the bottom of only the right-hand side of the screen. Currently it is covering the full screen, both left- and right-hand sides. 

--

Next set of updates on the Cash Flow module:

- The other "Less" lines (monthly expenses and all Automated Contributions) on the Household Cash Flow screen should be depicted as negative like the "Less Automated RRSP" and "Less Taxes & other".
- Indent the Automated contribution labels an extra tab under "Automated contributions:"
- An Enter when on Expenses or Household Cash Flow in the left-hand side should focus on the first focusable element on its right-hand side.

---

/work-on-slice @specs/work-product/slice-logs/2026-06-16-refinements-and-fixes.md

Next, for safety, I'd like the application to make a copy of the SQLite database on each startup within the user's config directory. Let me know if there are any decisions to be made first before doing this.

--

Updates on the splash screen and dashboard:
- Have the splash screen be skippable by pressing Enter. Add text to make it clear that's possible.
- Instead of using buttons on the dashboard, please use a more DOS-era menu. I've attached a screenshot of an old version of NetWare for reference. Our plain white border and colour scheme is fine, I'm interested in seeing the menu itself resemble this approach.

--

A few follow-up updates:
- Could you place a few more lines of space between "Amount Left to Invest" and the menu box
- When the date field has focus as depicted in the attached screenshot (or anything outside of the menu), could you make sure not to display a highlighted menu item in the menu box? As is, it's unclear as to where the focus is at.
- Could you update the contrast of the selected item: the highlight should be more grey, and the text of the highlighted item should match the blue of the background behind it (which follows the screenshot attached from the previous prompt). The menu items should be a brighter white when not focused too.
- Could you also shrink the Session Effective Date so that it's the same width as the dollar amount below it? (See the green alignment marking on the attached.) Please also keep the space between the left-hand labels and the and the right-hand components.

--

Closer:
- Please widen the right-hand side components so that the full date is visible.
- The background of a highlighted menu item doesn't have enough contrast still. Please make it the same blue as the menu box it's sitting in. 

--

Even better. Let's also:

- Put more horizontal space between the "Session Effective Date" label and its `DateInput`
- Let's wrap "Amount Left to Invest" is a bordered box too without a header. Within that box, let's also add "Current Net Worth" and "Total Net Worth"

I've included the current state of the dashboard for your reference. Please update the specifications to reflect the changes we're making in this session.

--

Let's just centre that metrics box on the screen (currently right-aligned to the Available Options box) and we should be good.

--

`get_dashboard_summary` in a core UI is a UI service method leaking across the core/application service boundary. Please fix that.

--

In the `general_service` we are introducing a `get_net_worths` method but we were already calculating those on the Balance Sheet screen. Are we duplicating logic here? If so, please remove it.

--

Finally, can you left align the labels in the summary box? Keep the values where they are.

---

/work-on-slice @specs/work-product/slice-logs/2026-06-16-refinements-and-fixes.md

Next enhancement: Pressing tab through all fields in a modal to get to the Create or Save button is tedious. Is it possible to add a universal shortcut in the modal mixin so that Ctrl+Enter is a shortcut to the affirmative action for the dialog? (Provided the form validates OK and that button is enabled, no-op otherwise.)

--

You were right, Ctrl+Enter isn't getting picked up. I updated the convention to be F10 in the code. Could you please add this to the TUI principles and anywhere else relevant in the harness?

---

/work-on-slice @specs/work-product/slice-logs/2026-06-16-refinements-and-fixes.md

I had Opus review this repo for my "Java accent" and it found a rather large one: the SQLAlchemy Session is being shared across the entire application like I would an `EntityManager` in JPA. This exposes us to a significant bug: although our service methods commit regularly, there's no exception handling. Meaning that a single exception in the application will result in a dirty session requiring the entire application to be restarted to work again.

Please assess the structure of the core services and how this can be better addressed. Please give me a few options to consider. Let's start an ADR for this change as well.

--

Looking at the code in @src/personal_finance/service/core/general_service.py  we're making a naked call on line 57 to `list_all_accounts(as_of)` -- I'm assuming this is to stuff the identity map? If each of the calls on lines 58 to 60 made that call itself, then that'd work too, right? We'd just be making 3x API calls? Weigh the option of caching the API calls instead so we can repeat that operation freely (assuming I've understood the crux of the problem). 

--

> correctness stops depending on the identity map at all. 

I like that.

>  so a CachingQuoteService decorator wrapping YahooFinanceQuoteService

I like that too. For `as_of` dates in the past, we're using end-of-day quotes, so those only ever need to be pulled once ever (per symbol). An `as_of` date of day should have a TTL of 5mins, though. Make sure that `SAME_DAY_QUOTE_TTL` in configurable, though. These heuristics can be baked into the `CachingQuoteService`.

Yes, please update the ADR. Assume that account data must always continue going through `balance_sheet_service` and never SQLAlchemy directly (we must have that documented somewhere already?). But now we extend that we'll make more liberal use of `_price_listed_securities` since it will be becoming much less expensive to use -- we don't need to rely on SQLAlchemy's identity map.

Let's get that into the ADR with a renewed analysis of any outstanding risks. Make sure we note in the ADR which specs need to be updated as a part of this too. I'll give it one further review and we can start putting this into place.

--

> Option 2 (session-per-operation) is no longer disqualified, but still needs a full audit for undocumented cross-call identity-map dependencies before it's safe to adopt with confidence. 

Option 2 is the most Pythonic, right? If so, let's go with that. Please perform the full audit to make sure we're OK to proceed.

--

Looks good to me, please proceed with updates.

---

/work-on-slice @specs/work-product/slice-logs/2026-06-16-refinements-and-fixes.md

Various refinements on the Goals screen:

- Centre "No goal" under the Goal heading.
- The dollar signs are not lining up between gold-bordered inputs and scalar inputs (see attached).

--

Uh-oh. The fix on the Goals screen (which was successful, thank you) appears to have broken the alignment between gold-bordered and scalar inputs on the Balance Sheet screen now.

--

> balance_sheet.py's .acct-balance-readonly class carried a padding: 0 2 override — a screen-specific hack added previously to compensate for MoneyInput's old default padding (0 2) not matching GoldBorderDisplay's default (0 1).

Can you assess this isn't happening anywhere else?

--

Can you make sure the Total value's cents in the Balance Sheet screen are right aligned with the cents in all the inputs above?

--

Right alignment is good. Can you now realign the dollar sign too?

---

/work-on-slice @specs/work-product/slice-logs/2026-06-16-refinements-and-fixes.md

Various refinements on the Goal Allocations screen. The "Actual $" and "Actual %" columns need better formatting:
  - Actual $ is correctly rounded to the nearest dollar -- perfect. But please make the width fixed with the dollar sign at the far left of the control so that they all line up together (the same formatting we use in our input boxes). Assume the largest value to display will be `$ 9,999,999`.
  - Actual % should be rounded to the nearest 10th of a percent. One position after the decimal should always be present (e.g., "2.0%").
  - If more spacing is required, then the Name column can be shrunk a bit. As you can see in the screenshot, there is some room there.

---

/work-on-slice @specs/work-product/slice-logs/2026-06-16-refinements-and-fixes.md

Next set of refinements:
- Allocation percentage should be right-aligned on the Investment Editor screen
- On Household Cash Flow, the right-hand side of the cents should line up. Right now, the bracket is lining up with the cents -- the closing bracket should be one character after the last cent.
- Add F5 to refresh the dashboard

---

Let's expand our sample data so that we have a dataset that uses all features of our application. Use what's currently in @scripts/seed_balance_sheet.py  as a base, but none of it is sacred -- please modify as necessary. Please feel free to create new files for each module, or just merge everything into a single `seed_sample_data.py` -- I have no preference.

Here are some guidelines:
  - Two profiles: mom and dad
  - Mom should make more money than dad. Say, $140,000 and $110,000, respectively.
  - Only dad has RRSP matching. Assume 5%. Contributed to the retirement goal. Assume it gets contributed to its own employer-provided RRSP account (separate from their personal ones).
  - But both have their own personal RRSP and TFSA direct investing accounts for retirement.
  - Assume both mom and dad own a variety of Canadian BMO and iSHARES equity and fixed income ETFs (no stocks). 
  - Assume a retirement asset allocation goal: 1.5% cash, 22% fixed income, 15% Canadian equity, 30% US equity, etc.
  - Assume the education goal is more balanced (for use in 10-15 years)
  - Dad owns the RESP for their child's education. He's contributed $500/month for the past five years.
  - They also have an emergency fund of $30k in a 3% unregistered 1YR cashable GIC.
  - Make sure the bank accounts are overclaimed by goals so we can show that warning in the screenshots, but by a reasonable amount.
  - Make the home worth $800,000. Leave a $200,000 mortgage on it.
  - Update credit card naming: "Mom's Visa" and "Dad's MasterCard"
  - Assume they have $6,000/month in total expenses. Create a bunch of reasonable expense line items to meet that.
  - They each own a car. Mom has a CR-V valued at $40k and dad has a $35k Camry.
  - Keep the numbers unrealistically round. This is sample data that'll be presented in an article -- I don't want anyone to think this is a sanitized version of my own household.
  - Let's have all our sample data entered as of July 2, 2026.

--

Two changes:
- Let's show one goal as in surplus: Education. It's currently hard coded at $200,000. Let's use a present value goal. Assume we need $100,000 by 2040 with savings starting in 2021 assuming a 5% return. That should get us into the green.
- Retirement shouldn't have its bank account difference filled. 

---

/work-on-slice @specs/work-product/slice-logs/2026-06-16-refinements-and-fixes.md

The visual design of this app is intentionally nostalgic of 90s-era DOS apps, especially Novell NetWare and IBM Classroom LAN Administration System. This is a quaint bit of my own personality leaking in, but I need it to also appear sharp by modern standards. I would like to create an ADR to refine the look-and-feel to make sure it's fully polished.

I've attached the screenshots for your initial review. Although there are two areas I'm already interested in:
  - Improve contrast of blues
  - Tighten the whitespace

Let's start with an analysis, some suggestions, and a plan.

-- 

Please proceed.

--

Two refinements:

- The title splash screen is hard to read as plain-old ASCII art. Can we use shaded block letters instead? Something like you'd see in ANSI art on a 90s era BBS.
- Does the green scroll bar look out of place? It's the only time that green is used which I'm unsure is a good thing, or a forgotten detail.