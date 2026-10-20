import { expect, test, type Page } from '@playwright/test';

async function ready(page: Page): Promise<void> {
  await expect(page.getByTestId('mode')).toContainText('Standalone');
  await expect(page.getByRole('button', { name: /save about 30,000/i })).toBeEnabled();
}

for (const [label, minLen] of [
  ['30,000', 30000],
  ['60,000', 60000],
] as const) {
  test(`standalone: save about ${label} characters, relaunch, checksum matches`, async ({ page }) => {
    await page.goto('/');
    await ready(page);
    await expect(page.getByTestId('entry')).toHaveText('ab-initio');

    await page.getByRole('button', { name: new RegExp(`save about ${label}`, 'i') }).click();
    await expect(page.getByTestId('result')).toContainText('Saved', { timeout: 30_000 });
    const ref = await page.getByTestId('stored-ref').textContent();
    expect(ref).toMatch(/^ags1;len=\d+;sha256=[0-9a-f]{64}$/);
    const len = Number(/len=(\d+)/.exec(ref ?? '')?.[1]);
    expect(len).toBeGreaterThanOrEqual(minLen);
    expect(len).toBeLessThanOrEqual(64000);

    await page.getByRole('button', { name: /exit session/i }).click();
    await page.reload();
    await ready(page);

    await expect(page.getByTestId('entry')).toHaveText('resume');
    await expect(page.getByTestId('stored-ref')).toHaveText(ref ?? '');
    // Auto-verify runs on load; the explicit button must agree.
    await expect(page.getByTestId('result')).toContainText('MATCH:');
    await page.getByRole('button', { name: /verify saved data/i }).click();
    await expect(page.getByTestId('result')).toContainText(`MATCH: ${len} of ${len} characters`);
    await expect(page.getByTestId('result')).toContainText('decodes OK');
  });
}

test('standalone: score and interactions are accepted and the score persists', async ({ page }) => {
  await page.goto('/');
  await ready(page);
  await page.getByRole('button', { name: /save about 30,000/i }).click();
  await expect(page.getByTestId('result')).toContainText('Saved', { timeout: 30_000 });

  await page.getByRole('button', { name: /report score/i }).click();
  await expect(page.getByTestId('result')).toContainText('Score sent: scaled 0.87');

  await page.getByRole('button', { name: /interaction records/i }).click();
  await expect(page.getByTestId('result')).toContainText('Interaction records written: 3');

  await page.reload();
  await ready(page);
  await expect(page.getByTestId('stored-score')).toHaveText('0.87');
  await expect(page.getByTestId('result')).toContainText('MATCH:');
});

test('every action is reachable from the keyboard', async ({ page }) => {
  await page.goto('/');
  await ready(page);
  const names = [
    /save about 30,000/i,
    /save about 60,000/i,
    /verify saved data/i,
    /report score/i,
    /interaction records/i,
    /exit session/i,
  ];
  for (const name of names) {
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name })).toBeFocused();
  }
  // Enter on the focused "Exit session" button ends the session.
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('result')).toContainText('Session ended');
});
