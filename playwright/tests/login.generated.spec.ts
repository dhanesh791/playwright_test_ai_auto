// Auto-generated sample Playwright test using locator_ai bundle.
import { test, expect } from '@playwright/test';
import { getLocator, locatorBundle } from '../locators.generated';

test('generated selectors resolve', async ({ page }) => {
  await page.goto('https://store.steampowered.com/login/?redir=&redir_ssl=1');
  for (const key of Object.keys(locatorBundle) as Array<keyof typeof locatorBundle>) {
    const locator = getLocator(page, key);
    await expect(locator).toBeVisible();
  }
});
