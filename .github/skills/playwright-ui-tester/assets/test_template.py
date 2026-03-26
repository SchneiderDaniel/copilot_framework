import pytest
from playwright.sync_api import Page, expect

def test_homepage(page: Page, base_url: str):
    """Verify that the homepage loads correctly."""
    page.goto(base_url)
    # expect(page).to_have_title("Your App Title")
    # expect(page.get_by_text("Welcome")).to_be_visible()
    
def test_navigation(page: Page, base_url: str):
    """Verify navigation to key pages."""
    page.goto(base_url)
    # page.click("text=Login")
    # expect(page).to_have_url(f"{base_url}/login")
