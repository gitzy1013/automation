from typing import Generator

import pytest

from playwright.sync_api import Page, expect

from .utils import (
    assert_number_of_todos_in_local_storage,
    check_number_of_completed_todos_in_local_storage,
    create_default_todos,
)


@pytest.fixture(autouse=True)
def run_around_tests(page: Page) -> Generator[None, None, None]:
    page.goto("https://demo.playwright.dev/todomvc")
    yield


def test_should_allow_me_to_mark_all_items_as_completed(page: Page) -> None:
    create_default_todos(page)
    assert_number_of_todos_in_local_storage(page, 3)
    # Complete all todos.
    page.locator(".toggle-all").check()

    # Ensure all todos have 'completed' class.
    expect(page.locator(".todo-list li")).to_have_class(
        ["completed", "completed", "completed"]
    )
    check_number_of_completed_todos_in_local_storage(page, 3)
    assert_number_of_todos_in_local_storage(page, 3)


def test_should_allow_me_to_clear_the_complete_state_of_all_items(page: Page) -> None:
    create_default_todos(page)
    assert_number_of_todos_in_local_storage(page, 3)
    # Check and then immediately uncheck.
    page.locator(".toggle-all").check()
    page.locator(".toggle-all").uncheck()

    # Should be no completed classes.
    expect(page.locator(".todo-list li")).to_have_class(["", "", ""])
    assert_number_of_todos_in_local_storage(page, 3)


def test_complete_all_checkbox_should_update_state_when_items_are_completed_or_cleared(
    page: Page,
) -> None:
    create_default_todos(page)
    assert_number_of_todos_in_local_storage(page, 3)
    toggleAll = page.locator(".toggle-all")
    toggleAll.check()
    expect(toggleAll).to_be_checked()
    check_number_of_completed_todos_in_local_storage(page, 3)

    # Uncheck first todo.
    firstTodo = page.locator(".todo-list li").nth(0)
    firstTodo.locator(".toggle").uncheck()

    # Reuse toggleAll locator and make sure its not checked.
    expect(toggleAll).not_to_be_checked()

    firstTodo.locator(".toggle").check()
    check_number_of_completed_todos_in_local_storage(page, 3)

    # Assert the toggle all is checked again.
    expect(toggleAll).to_be_checked()
    assert_number_of_todos_in_local_storage(page, 3)
