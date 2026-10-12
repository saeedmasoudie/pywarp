from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt, Slot


class ObjectListModel(QAbstractListModel):
    def __init__(
        self,
        roles: tuple[str, ...],
        max_items: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self._roles = {
            Qt.UserRole + index + 1: role
            for index, role in enumerate(roles)
        }
        self._items: list[dict] = []
        self._max_items = max_items

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            role_id: QByteArray(role.encode())
            for role_id, role in self._roles.items()
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        role_name = self._roles.get(role)
        return self._items[index.row()].get(role_name) if role_name else None

    def replace(self, items: list[dict]) -> None:
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def append(self, item: dict) -> None:
        if self._max_items and len(self._items) >= self._max_items:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self._items.pop(0)
            self.endRemoveRows()
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(item)
        self.endInsertRows()

    def remove_matching(self, **values) -> None:
        for row in range(len(self._items) - 1, -1, -1):
            if all(self._items[row].get(key) == value for key, value in values.items()):
                self.beginRemoveRows(QModelIndex(), row, row)
                self._items.pop(row)
                self.endRemoveRows()

    @Slot()
    def clear(self) -> None:
        self.replace([])
