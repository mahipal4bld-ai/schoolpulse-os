# Playwright UI check (Expo web preview): invalid event start/end times must disable Save draft + Publish.
# Run via the screenshot/e2e harness against the preview URL. Last run: PASS (see docs/M3_PROGRESS.md).
async def run(page):
    await page.set_viewport_size({"width": 390, "height": 844})

    async def dis(tid):
        return (await page.get_by_test_id(tid).get_attribute("aria-disabled")) == "true"

    await page.get_by_placeholder("you@school.in").fill("principal@sunrise.demo")
    await page.locator("input[type=password]").fill("Demo@1234")
    await page.get_by_text("Sign in", exact=True).click()
    await page.get_by_test_id("quick-calendar").click()
    await page.get_by_test_id("new-event-button").click()
    await page.get_by_test_id("event-title-input").fill("ETEST UI validation")
    assert not await dis("event-publish")
    await page.get_by_test_id("event-start-time-input").click()
    await page.get_by_test_id("event-start-time-input-opt-1000").click()
    await page.get_by_test_id("event-end-time-input").click()
    await page.get_by_test_id("event-end-time-input-typed").fill("09:00")   # validated typed fallback
    await page.get_by_test_id("event-end-time-input-apply").click()
    assert await dis("event-publish") and await dis("event-save-draft")
    assert await page.get_by_text("End time must be after the start time").count() == 1
    await page.get_by_test_id("event-end-time-input").click()
    await page.get_by_test_id("event-end-time-input-opt-1130").click()
    assert not await dis("event-publish") and not await dis("event-save-draft")
