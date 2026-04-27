"""E2E tests for /explainer page (live server required at http://localhost:8765)."""
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8765"

SCENARIO_IDS_AND_ACTIONS = [
    ("confident-bid", "RAISE"),
    ("challenge-aggressor", "CHALLENGE"),
    ("spot-on-spike", "SPOT ON"),
    ("blind-aggression-trigger", "CHALLENGE"),
    ("pressure-opportunity", "RAISE"),
]


def test_explainer_page_loads(page: Page):
    page.goto(f"{BASE_URL}/explainer")
    expect(page.locator("h1")).to_contain_text("CPU LOGIC EXPLAINER")
    expect(page.locator("#picker-section")).to_be_visible()
    expect(page.locator("#step-section")).to_be_hidden()


def test_picker_populates_five_cards(page: Page):
    page.goto(f"{BASE_URL}/explainer")
    expect(page.locator("#picker-cards .picker-card")).to_have_count(5, timeout=5000)


def test_step_navigation_full_flow(page: Page):
    page.goto(f"{BASE_URL}/explainer")
    page.locator("#picker-cards .picker-card").first.click()
    expect(page.locator("#step-section")).to_be_visible()
    expect(page.locator("#step-counter")).to_contain_text("STEP 1 OF 6")

    for expected_step in range(2, 7):
        page.locator("#btn-next").click()
        expect(page.locator("#step-counter")).to_contain_text(f"STEP {expected_step} OF 6")

    expect(page.locator(".decision-action")).to_be_visible()
    expect(page.locator("#btn-next")).to_be_disabled()

    page.locator("#btn-prev").click()
    expect(page.locator("#step-counter")).to_contain_text("STEP 5 OF 6")


@pytest.mark.parametrize("scenario_id, expected_action", SCENARIO_IDS_AND_ACTIONS)
def test_each_scenario_renders_decision(page: Page, scenario_id: str, expected_action: str):
    page.goto(f"{BASE_URL}/explainer")
    card = page.locator(f'.picker-card[data-scenario-id="{scenario_id}"]')
    expect(card).to_be_visible(timeout=5000)
    card.click()
    for _ in range(5):
        page.locator("#btn-next").click()
    expect(page.locator(".decision-action")).to_contain_text(expected_action)


def test_back_to_picker_returns_to_card_view(page: Page):
    page.goto(f"{BASE_URL}/explainer")
    page.locator("#picker-cards .picker-card").first.click()
    expect(page.locator("#step-section")).to_be_visible()
    page.locator("#btn-back-to-picker").click()
    expect(page.locator("#picker-section")).to_be_visible()
    expect(page.locator("#step-section")).to_be_hidden()


def test_lobby_link_to_explainer(page: Page):
    page.goto(BASE_URL)
    link = page.locator('a[href="/explainer"]')
    expect(link).to_be_visible()
    expect(link).to_contain_text("CPU LOGIC EXPLAINER")
