"""Streamlit 앱 실행 진입점.

UI 구현은 `legal_rag.ui.streamlit_app` 내부에 두고, 이 파일은
`streamlit run app.py`라는 일관된 실행 경로만 제공한다.
"""

from legal_rag.ui.streamlit_app import main


if __name__ == "__main__":
    main()

