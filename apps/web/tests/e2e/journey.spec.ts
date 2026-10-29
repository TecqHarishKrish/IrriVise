import { expect, test, type Page } from '@playwright/test';

async function waitForJob(page: Page) {
  await expect(page.getByText(/^succeeded$/i).first()).toBeVisible({ timeout: 180_000 });
}

test('complete offline research journey', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));

  // 1–3. First launch → sample field (synthetic data) → a fixed-schedule run is queued automatically
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Welcome to IrriVise' })).toBeVisible();
  await page.getByRole('button', { name: /Explore sample field/ }).click();
  await expect(page).toHaveURL(/\/simulation/);

  // 4–5. Fixed-schedule run completes in the worker; KPIs, charts and daily records come from the saved trace
  await waitForJob(page);
  await expect(page.getByText('B0', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('img', { name: 'Root-zone soil water — twin belief' })).toBeVisible();
  await expect(page.getByRole('table', { name: 'Saved daily simulation records' })).toContainText('2020-06-15');
  await page.getByRole('button', { name: 'Next day' }).click();
  await expect(page.getByText('Day 2/140')).toBeVisible();

  // 6. Train a quick PPO model (functional smoke test)
  await page.getByRole('link', { name: 'Model Training Lab' }).click();
  await page.locator('summary', { hasText: 'Advanced hyperparameters' }).click();
  await page.getByLabel('Total timesteps (per seed)').fill('2048');
  await page.getByRole('button', { name: 'Queue training' }).click();
  await waitForJob(page);
  await expect(page.getByText(/cpu_quick · seed 42/).first()).toBeVisible();
  await expect(page.getByRole('img', { name: 'Logged learning curve' })).toBeVisible();

  // 7. Execute a CARAT-controlled season with the trained model
  await page.getByRole('link', { name: 'Irrigation Simulator' }).click();
  await page.getByLabel('Controller / method').selectOption('carat_full');
  await page.getByLabel(/Evaluate schedule in/).click();
  await page.getByRole('button', { name: 'Queue simulation' }).click();
  await waitForJob(page);
  await expect(page.getByText('Full CARAT (PPO + VOI readings + correction + risk)', { exact: true })).toBeVisible();

  // 8. Inspect observation decisions and twin corrections in the CARAT Decision Lab
  await page.getByRole('link', { name: 'CARAT Decision Lab' }).click();
  await expect(page.getByRole('heading', { name: 'Why this decision?' })).toBeVisible();
  await page.getByRole('tab', { name: 'Regret & VOI' }).click();
  await expect(page.getByText('Expected regret after', { exact: true })).toBeVisible();
  await page.getByRole('tab', { name: 'Twin correction' }).click();
  await page.getByRole('tab', { name: 'Risk manager' }).click();
  await expect(page.getByText(/hard-projected/)).toBeVisible();
  await page.getByLabel(/Post-run evaluation/).click();
  await expect(page.getByText('Simulated reference · evaluation only').first()).toBeVisible();

  // 9. Compare against a baseline on held-out seasons
  await page.getByRole('link', { name: 'Experiment Benchmark' }).click();
  await page.getByRole('checkbox', { name: 'Soil-moisture threshold (MAD rule)' }).click();
  await page.getByRole('checkbox', { name: /CARAT planner/ }).click();
  await page.getByRole('checkbox', { name: /Full CARAT/ }).click();
  await page.getByLabel('Seeds').fill('1');
  await page.getByRole('button', { name: 'Queue experiment' }).click();
  await expect(page.getByRole('heading', { name: 'What did the data show?' })).toBeVisible({ timeout: 180_000 });
  await expect(page.getByText(/Paired differences vs fixed_schedule/)).toBeVisible();

  // 10. Export actual results with the reproducibility manifest
  await page.getByRole('link', { name: 'Report & Export Center' }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Generate & download' }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.zip$/);
  await expect(page.getByText(/sha256 [0-9a-f]{16}/).first()).toBeVisible();

  expect(errors).toEqual([]);
});

test('mobile navigation and theme toggle', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/settings');
  await page.getByRole('button', { name: 'Open navigation' }).click();
  const dialog = page.getByRole('dialog', { name: 'Navigation menu' });
  await dialog.getByRole('link', { name: 'Weather & Data Studio' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Weather & Data Studio' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.getByRole('button', { name: /Switch to dark theme/ }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
});

test('keyboard users can skip to content and reach every page', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  for (const label of ['Projects & Fields', 'Digital Twin Studio', 'Insights & Analytics', 'Settings & Help']) {
    await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: label }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { level: 1, name: label })).toBeVisible();
  }
});
