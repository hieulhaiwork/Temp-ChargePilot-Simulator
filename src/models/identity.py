"""Bản ghi tài khoản nội bộ — KHÔNG phải DTO của API.

Vì sao tách khỏi src/models/api.py: model này mang `password_hash` và `email`. Để riêng một
module thì không router nào vô tình dùng nó làm response_model. API trả UserProfile /
ResidentProfile (src/models/api.py), chỉ có `user_id` giả danh (NFR riêng tư).
"""

from pydantic import AwareDatetime, BaseModel, Field

from src.models.charging import ConsentScope
from src.models.control import Role


class UserRecord(BaseModel):
    user_id: str = Field(min_length=1, description="Mã giả danh, vd res-1a2b3c4d — dùng ở mọi bảng nghiệp vụ")
    email: str = Field(min_length=3, max_length=254, description="Chữ thường; chỉ bảng users chứa email")
    password_hash: str | None = Field(default=None, description="Chuỗi scrypt; None sau khi tài khoản bị xoá")
    role: Role
    display_name: str = Field(min_length=1, max_length=80)
    vehicle_model: str | None = None
    default_soc_target: float | None = Field(default=None, gt=0, le=100)
    consent: ConsentScope = Field(default_factory=ConsentScope)
    created_at: AwareDatetime
    deleted_at: AwareDatetime | None = None
