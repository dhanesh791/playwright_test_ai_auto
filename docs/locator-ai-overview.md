# Locator AI Overview (Manager Brief)

## Goal
Keep Playwright tests stable even when the product team changes HTML IDs or
classes. Instead of QA engineers chasing broken selectors, the Locator AI tool
scans the latest build, finds the right UI elements automatically, and refreshes
the selectors that Playwright uses.

## How it works (plain English)
1. **Take a snapshot of the page** – We open the site in an automated browser
   (Playwright) and collect details about every button, input, or dropdown.
2. **Understand each element** – We look at labels, surrounding text, and other
   clues. A small AI model (from Hugging Face) helps match human-friendly names
   like “username field” or “Sign in button” to the correct element, even if the
   HTML changed.
3. **Generate new selectors** – For every element we care about, we create a new
   CSS/XPath-style locator and double-check that it points to exactly one object
   on the page.
4. **Update Playwright helpers** – The tool writes a single TypeScript file that
   Playwright tests import. Test authors keep using stable semantic names (e.g.
   `getLocator(page, 'login.username')`). The underlying selector updates are
   automatic.
5. **Optional: discover everything** – When we want coverage of a new page, we
   can ask the tool to label every interactive element. That makes it quick to
   onboard new screens or to spot renamed controls.

## Day-to-day workflow
- **Before running Playwright tests** (locally or in CI):
  ```powershell
  python -m locator_ai --url "https://app-under-test.example" \
    --out artifacts\locators.json \
    --update-playwright
  ```
  *Result:* Fresh selectors saved to JSON + the Playwright helper file.

- **For unidentified pages:** add `--discover-all` once to auto-name every
  control. Rename the interesting keys in Playwright if desired, then continue
  using the normal command.

- **When something changes unexpectedly:** the tool flags elements it cannot
  resolve (`status = needs_review`). QA can investigate that specific control.

## Benefits
- **Less manual maintenance** – selectors refresh with one command or CI job.
- **Stable Playwright code** – tests reference semantic names, not brittle IDs.
- **Fast onboarding** – discovery mode bootstraps new pages in minutes.
- **Ready for CI** – run the command in pipelines; commit or publish the updated
  files so every test run stays up-to-date.

## Rollout checklist
1. Agree on the semantic names QA wants to use (e.g., `coverNoteType`).
2. Add those names to `locator_ai/config.py` once.
3. Update Playwright specs to call `getLocator(page, '<name>')`.
4. Add the CLI command to the build pipeline (before tests).
5. Monitor the generated JSON for `needs_review` entries and only triage those.

That’s it—the team spends time testing features, not chasing CSS selectors.
