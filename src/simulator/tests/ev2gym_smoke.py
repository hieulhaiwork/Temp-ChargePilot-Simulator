"""Smoke test EV2Gym thật, không cần dịch vụ bên ngoài.

Chạy từ thư mục gốc dự án:
    .simulator/bin/python src/simulator/tests/ev2gym_smoke.py
Hoặc nếu môi trường có pytest:
    python -m pytest src/simulator/tests/ev2gym_smoke.py -v -s
"""

from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory


def test_ev2gym_smoke() -> None:
    """Kiểm tra import, khởi tạo, reset, action space và 5 bước mô phỏng."""
    import numpy as np
    import yaml
    from ev2gym.models.ev2gym_env import EV2Gym

    seed = 42
    n_steps = 5
    package = files("ev2gym")
    config = yaml.safe_load(package.joinpath("example_config_files/PublicPST.yaml").read_text())
    config.update(
        number_of_charging_stations=2,
        random_day=False,
        random_hour=False,
        ev_specs_file=str(package.joinpath("data/ev_specs_ev_plus_phev.json")),
    )

    # Giữ cấu hình mẫu trong package nguyên vẹn; không phụ thuộc thư mục chạy.
    with TemporaryDirectory(prefix="ev2gym-smoke-") as temp_dir:
        config_path = Path(temp_dir) / "smoke.yaml"
        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
        env = EV2Gym(
            config_file=str(config_path),
            seed=seed,
            save_replay=False,
            save_plots=False,
            render_mode=None,
            verbose=False,
        )
        try:
            observation, info = env.reset(seed=seed)
            assert isinstance(info, dict), "reset() phải trả về info dạng dict"
            assert env.current_step == 0, "reset() chưa đưa mô phỏng về bước 0"
            assert env.observation_space.contains(observation), "Observation không đúng space"
            assert np.isfinite(observation).all(), "Observation chứa NaN/Inf"
            assert len(env.charging_stations) == 2, "Không tạo đủ trạm sạc"

            env.action_space.seed(seed)
            total_reward = 0.0
            for step in range(1, n_steps + 1):
                action = env.action_space.sample()
                assert env.action_space.contains(action), "Action mẫu không hợp lệ"
                observation, reward, terminated, truncated, info = env.step(action)
                assert env.current_step == step, "step() không tăng bước mô phỏng"
                assert env.observation_space.contains(observation), "Observation không đúng space"
                assert np.isfinite(observation).all(), "step() trả về NaN/Inf"
                assert np.isscalar(reward) and np.isfinite(reward), "Reward không hợp lệ"
                assert isinstance(info, dict), "step() phải trả về info dạng dict"
                assert isinstance(terminated, (bool, np.bool_)), "terminated không phải boolean"
                assert isinstance(truncated, (bool, np.bool_)), "truncated không phải boolean"
                assert not (terminated or truncated), "Episode kết thúc sớm ngoài dự kiến"
                total_reward += float(reward)

            observation, info = env.reset(seed=seed)
            assert env.current_step == 0, "Không reset được sau khi chạy mô phỏng"
            assert env.observation_space.contains(observation), "Observation sau reset không hợp lệ"
            assert np.isfinite(observation).all(), "Observation sau reset chứa NaN/Inf"
        finally:
            env.close()

    print(
        f"PASS: EV2Gym import/init/reset/action_space/step/close; "
        f"stations=2, steps={n_steps}, total_reward={total_reward:.4f}"
    )


if __name__ == "__main__":
    test_ev2gym_smoke()
