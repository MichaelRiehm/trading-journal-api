import uuid
from collections.abc import Sequence
from typing import NoReturn

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trading_journal.domain.errors import ConflictError, NotFoundError
from trading_journal.models import Strategy
from trading_journal.repositories import StrategyRepository
from trading_journal.schemas.strategy import StrategyCreate, StrategyUpdate
from trading_journal.services._db_errors import violated_constraint

_DUPLICATE_NAME = "You already have a strategy with this name"


class StrategyService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._strategies = StrategyRepository(session)

    def create(self, user_id: uuid.UUID, data: StrategyCreate) -> Strategy:
        if self._strategies.get_by_name(user_id, data.name) is not None:
            raise ConflictError(_DUPLICATE_NAME)
        try:
            strategy = self._strategies.add(
                user_id=user_id, name=data.name, description=data.description
            )
        except IntegrityError as exc:
            self._raise_for_integrity_error(exc)
        self._session.commit()
        return strategy

    def get(self, user_id: uuid.UUID, strategy_id: uuid.UUID) -> Strategy:
        strategy = self._strategies.get(user_id, strategy_id)
        if strategy is None:
            raise NotFoundError("Strategy")
        return strategy

    def list(self, user_id: uuid.UUID) -> Sequence[Strategy]:
        return self._strategies.list(user_id)

    def update(self, user_id: uuid.UUID, strategy_id: uuid.UUID, data: StrategyUpdate) -> Strategy:
        strategy = self.get(user_id, strategy_id)
        changes = data.model_dump(exclude_unset=True)
        new_name = changes.get("name")
        renamed_to = new_name if new_name is not None and new_name != strategy.name else None
        if renamed_to and self._strategies.get_by_name(user_id, renamed_to) is not None:
            raise ConflictError(_DUPLICATE_NAME)
        for field, value in changes.items():
            setattr(strategy, field, value)
        try:
            self._strategies.save(strategy)
        except IntegrityError as exc:
            self._raise_for_integrity_error(exc)
        self._session.commit()
        return strategy

    def delete(self, user_id: uuid.UUID, strategy_id: uuid.UUID) -> None:
        strategy = self.get(user_id, strategy_id)
        if self._strategies.has_trades(user_id, strategy_id):
            # The RESTRICT foreign key would refuse anyway; this gives a clear message.
            raise ConflictError("Strategy has trades. Reassign or delete them first")
        self._strategies.delete(strategy)
        self._session.commit()

    def _raise_for_integrity_error(self, exc: IntegrityError) -> NoReturn:
        # A concurrent request got past the pre-check; the unique constraint caught it.
        self._session.rollback()
        if violated_constraint(exc) == "uq_strategies_user_id_name":
            raise ConflictError(_DUPLICATE_NAME) from exc
        raise exc
