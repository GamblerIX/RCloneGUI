import re
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class Remote:

    name: str
    type: str
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            raise ValueError("远程存储名称不能为空")
        if not re.match(r'^[a-zA-Z0-9_-]+$', self.name):
            raise ValueError(f"无效的远程存储名称: {self.name}。只能包含字母、数字、下划线和连字符。")

        if not self.type:
            raise ValueError("远程存储类型不能为空")
        if not re.match(r'^[a-z0-9]+$', self.type.lower()):
            raise ValueError(f"无效的远程存储类型: {self.type}")

        if not isinstance(self.config, dict):
            object.__setattr__(self, 'config', {})

    @property
    def host(self) -> Optional[str]:
        return self.config.get('host') or self.config.get('url')

    @property
    def user(self) -> Optional[str]:
        return self.config.get('user') or self.config.get('username')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'type': self.type,
            'config': dict(self.config)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Remote':
        if 'name' not in data:
            raise KeyError("缺少必需字段: 'name'")
        if 'type' not in data:
            raise KeyError("缺少必需字段: 'type'")

        return cls(
            name=data['name'],
            type=data['type'],
            config=data.get('config', {})
        )

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Remote):
            return NotImplemented
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)
