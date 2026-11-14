import {test, expect} from "@playwright/test";

test("brief, six age bands and honest runtime status", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "Prima il pubblico. Poi la campagna."})).toBeVisible();
  await page.getByRole("button", {name: "Nuova simulazione", exact: true}).first().click();
  await expect(page.getByLabel("Nome della campagna")).toBeVisible();
  await page.getByLabel("Nome della campagna").fill("Test Playwright");
  await expect(page.getByLabel("Descrizione del prodotto")).not.toHaveValue("");
  await page.getByRole("main").getByRole("button", {name: "Pubblico e ipotesi"}).click();
  for (const band of ["18–24", "25–34", "35–44", "45–54", "55–64", "65+"]) {
    await expect(page.getByText(band, {exact: true}).first()).toBeVisible();
  }
  await expect(page.getByText(/20 agenti per fascia/)).toBeVisible();
});

test("responsive navigation and empty history", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/");
  await page.getByRole("button", {name: "Storico run", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Le tue simulazioni"})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
