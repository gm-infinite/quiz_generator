"""Gradio entry point.

python app.py
"""
from ui.views import CSS, build_blocks


def main() -> None:
    build_blocks().launch(css=CSS)


if __name__ == "__main__":
    main()
