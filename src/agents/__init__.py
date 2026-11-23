"""Dành cho AI module phía vận hành: AI-1 negotiation và AI-4 decision copilot (ADR-019). Chưa có code.

Chat cư dân (LangGraph ReAct + HITL) nằm ở `src/llm_chat/`; LLM provider dùng chung ở `src/services/llm.py`.
Ranh giới (khoá ở `tests/test_architecture.py`): chỉ đi qua `src/services`, không tạo `Command`, không bypass Guard,
không chạm DB / actuator / simulator / optimizer trực tiếp.
"""
