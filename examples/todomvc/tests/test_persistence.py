from typing import Generator

import pytest

from playwright.sync_api import Page, expect

from .utils import TODO_ITEMS, check_number_of_completed_todos_in_local_storage


@pytest.fixture(autouse=True)
def run_around_tests(page: Page) -> Generator[None, None, None]:
    page.goto("https://demo.playwright.dev/todomvc")
    yield


def test_should_persist_its_data(page: Page) -> None:
    for item in TODO_ITEMS[:2]:
        page.locator(".new-todo").fill(item)
        page.locator(".new-todo").press("Enter")

    todo_items = page.locator(".todo-list li")
    todo_items.nth(0).locator(".toggle").check()
    expect(todo_items).to_have_text([TODO_ITEMS[0], TODO_ITEMS[1]])
    expect(todo_items).to_have_class(["completed", ""])

    # Ensure there is 1 completed item.
    check_number_of_completed_todos_in_local_storage(page, 1)

    # Now reload.
    page.reload()
    expect(todo_items).to_have_text([TODO_ITEMS[0], TODO_ITEMS[1]])
    expect(todo_items).to_have_class(["completed", ""])
