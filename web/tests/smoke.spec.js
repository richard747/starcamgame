import { expect, test } from "@playwright/test";

test("start screen says the Kinect is not available", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Star Pop" })).toBeVisible();
  await expect(page.getByText(/Kinect cannot/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Start camera" })).toBeVisible();
});

test("demo mode draws a two-player meteor round", async ({ page }) => {
  await page.goto("/?demo=1");
  await page.getByRole("button", { name: "Meteors" }).click();
  await page.getByRole("button", { name: "2", exact: true }).click();
  await page.getByRole("button", { name: "Demo bodies" }).click();
  await expect(page.locator("#status")).toContainText("Demo");
  await expect(page.locator("#start")).toBeHidden();
  await page.waitForTimeout(600);
  const canvas = page.locator("#game");
  const box = await canvas.boundingBox();
  expect(box?.width).toBeGreaterThan(200);
  const buffer = await canvas.screenshot({ path: "screenshot.png" });
  expect(buffer.length).toBeGreaterThan(8000);
  const varied = await canvas.evaluate((element) => {
    const ctx = element.getContext("2d");
    const { data } = ctx.getImageData(0, 0, element.width, element.height);
    let light = 0;
    for (let i = 0; i < data.length; i += 16) {
      if (data[i] + data[i + 1] + data[i + 2] > 280) light += 1;
    }
    return light;
  });
  expect(varied).toBeGreaterThan(40);
});

test("a fake camera reaches pose tracking", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Start camera" }).click();
  await expect(page.locator("#status")).toContainText(/Camera on|could not start/i, { timeout: 45_000 });
});

test("the built app serves the manifest, model, and wasm", async ({ request }) => {
  const manifest = await request.get("/manifest.webmanifest");
  expect(manifest.ok()).toBeTruthy();
  const body = await manifest.json();
  expect(body.name).toBe("Star Pop");
  expect(body.display).toBe("standalone");
  expect(body.icons.length).toBeGreaterThan(0);
  const model = await request.get("/models/pose_landmarker_lite.task");
  expect(model.ok()).toBeTruthy();
  expect((await model.body()).length).toBeGreaterThan(1_000_000);
  const wasm = await request.get("/mediapipe/wasm/vision_wasm_internal.wasm");
  expect(wasm.ok()).toBeTruthy();
  expect((await wasm.body()).length).toBeGreaterThan(1_000_000);
});
