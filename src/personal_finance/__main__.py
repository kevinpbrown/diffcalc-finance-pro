"""Entry point for the Personal Finance TUI application."""


def main() -> None:
    """Launch the application."""
    from personal_finance.ui.app import PersonalFinanceApp

    app = PersonalFinanceApp()
    app.run()


if __name__ == "__main__":
    main()
