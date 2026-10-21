"""Streamlit UI 구조.

Streamlit 의존성을 설치하기 전에도 패키지 테스트가 가능하도록
import를 main 내부에서 지연한다.
"""


def main() -> None:
    try:
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError("Streamlit UI 의존성이 아직 설치되지 않았습니다.") from exc

    st.set_page_config(page_title="생활법률 판례 내비게이터", page_icon="⚖️")
    st.title("⚖️ 생활법률 판례 내비게이터")
    st.info("현재 아키텍처와 개인정보 보호 경계를 구현하는 단계입니다.")

