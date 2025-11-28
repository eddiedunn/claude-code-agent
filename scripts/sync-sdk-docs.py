#!/usr/bin/env python3
"""
Sync Claude Agent SDK documentation from platform.claude.com.

This script fetches documentation pages using Playwright to execute JavaScript
and simulate clicking the "Copy page" button to get markdown content.

Requirements:
    uv pip install playwright
    playwright install chromium

Usage:
    uv run python scripts/sync-sdk-docs.py
"""

import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("ERROR: Playwright not available.")
    print("Install with: uv pip install playwright")
    print("Then run: playwright install chromium")
    sys.exit(1)

DOCS_BASE = "https://platform.claude.com/docs/en/api/agent-sdk"
DOCS_DIR = Path(__file__).parent.parent / "docs" / "sdk"

# Map page URLs to local filenames
SDK_DOCS = {
    "overview.md": f"{DOCS_BASE}/overview",
    "python-reference.md": f"{DOCS_BASE}/python",
    "typescript-reference.md": f"{DOCS_BASE}/typescript",
    "streaming-input.md": f"{DOCS_BASE}/streaming-vs-single-mode",
    "handling-permissions.md": f"{DOCS_BASE}/permissions",
    "session-management.md": f"{DOCS_BASE}/sessions",
    "structured-outputs.md": f"{DOCS_BASE}/structured-outputs",
    "hosting.md": f"{DOCS_BASE}/hosting",
    "modifying-system-prompts.md": f"{DOCS_BASE}/modifying-system-prompts",
    "mcp.md": f"{DOCS_BASE}/mcp",
    "custom-tools.md": f"{DOCS_BASE}/custom-tools",
    "subagents.md": f"{DOCS_BASE}/subagents",
    "slash-commands.md": f"{DOCS_BASE}/slash-commands",
    "agent-skills.md": f"{DOCS_BASE}/skills",
    "tracking-costs-and-usage.md": f"{DOCS_BASE}/cost-tracking",
    "todo-lists.md": f"{DOCS_BASE}/todo-tracking",
    "plugins.md": f"{DOCS_BASE}/plugins",
}


def extract_markdown_with_playwright(url: str) -> str | None:
    """
    Use Playwright to load the page and simulate the copy markdown button click.

    The platform.claude.com site has a "Copy page" button that generates markdown.
    We'll use Playwright to click it and capture the clipboard content.
    """
    with sync_playwright() as p:
        # Launch browser in headless mode
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # Grant clipboard permissions
        context.grant_permissions(['clipboard-read', 'clipboard-write'])

        page = context.new_page()

        try:
            print(f"  Loading page...")
            page.goto(url, wait_until='networkidle', timeout=30000)

            # Wait for content to load
            page.wait_for_selector('main', timeout=10000)

            # Look for the copy markdown button
            # It might be in a dropdown menu or directly accessible
            # Try to find it by text or aria-label

            try:
                # Try to find and click the dropdown/menu button first
                menu_button = page.locator('button[aria-haspopup="menu"]').first
                if menu_button.is_visible(timeout=2000):
                    menu_button.click()
                    time.sleep(0.5)  # Wait for menu to open

                # Now try to find the copy markdown option
                # Look for text containing "markdown" or "copy page"
                copy_button = page.get_by_text('Copy page', exact=False).first
                if copy_button.is_visible(timeout=2000):
                    copy_button.click()
                    time.sleep(0.5)  # Wait for copy to complete

                    # Get clipboard content
                    markdown = page.evaluate('navigator.clipboard.readText()')
                    return markdown

            except PlaywrightTimeout:
                print("  Could not find copy button, trying alternative method...")

            # Alternative: Extract markdown from page structure directly
            # Look for the main content area and convert to markdown
            main_content = page.locator('main').first
            if main_content:
                # Get the text content as fallback
                text_content = main_content.inner_text()
                return f"# Content extracted from {url}\n\n{text_content}\n\n<!-- Note: This may need manual formatting -->"

            return None

        except Exception as e:
            print(f"  Error: {e}")
            return None
        finally:
            browser.close()


def sync_sdk_docs():
    """Sync all SDK documentation."""
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright is required but not available.")
        sys.exit(1)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print("Syncing Claude Agent SDK documentation from platform.claude.com...")
    print(f"Target directory: {DOCS_DIR}")
    print()
    print("Using Playwright to extract markdown content...")
    print("This may take a few minutes as we load each page.\n")

    synced = 0
    failed = 0

    for local_name, url in SDK_DOCS.items():
        print(f"Fetching: {local_name}")
        markdown = extract_markdown_with_playwright(url)

        if markdown and len(markdown.strip()) > 100:
            # Write to file
            output_path = DOCS_DIR / local_name
            output_path.write_text(markdown)
            print(f"✓ Synced: {local_name} ({len(markdown)} characters)\n")
            synced += 1
        else:
            print(f"✗ Failed: {local_name} (no content extracted)\n")
            failed += 1

    print()
    print(f"Sync complete: {synced} synced, {failed} failed")

    if failed > 0:
        print("\nSome pages failed to sync. You may need to:")
        print("1. Check your internet connection")
        print("2. Manually copy content using the 'Copy page' button")
        print("3. Update the script if the page structure has changed")
        sys.exit(1)


if __name__ == "__main__":
    sync_sdk_docs()
