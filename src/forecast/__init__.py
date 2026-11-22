"""Dự báo thời điểm rút đầu nối (F6, Should) — hướng AI nghiên cứu chính. Owner: TV2.

Câu hỏi nghiên cứu (PRD §8, MT7): dự báo lúc xe RÚT đầu nối có giúp bộ tối ưu xếp
hàng đợi tốt hơn không? Đo bằng MAE dự báo + so C (có ML) với B (không ML).

    datasets.py   nạp & chuẩn hoá Na Uy 2024/2021, ACN-Data → ChargingSession (T1.3)
    features.py   feature không rò rỉ nhãn (FR17)
    predict.py    DepartureForecaster: giờ khai báo, trung vị lịch sử, LightGBM
    train.py      CLI huấn luyện LightGBM → artifacts/ (T2.3)
    evaluate.py   MAE + phân tích ca thất bại (T2.3, T4.1)

Ranh giới: không import agents/api/guard/simulator/optimizer (tests/test_architecture.py).
FR9: dự báo KHÔNG BAO GIỜ được nới deadline cư dân đã khai báo.
"""
