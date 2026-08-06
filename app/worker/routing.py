# """
# File: app/worker/routing.py

# Centralized Celery task-routing and queue configuration.

# This module defines:

# - broker exchange configuration,
# - durable worker queues,
# - task-to-queue routing rules,
# - queue-construction helpers,
# - and startup validation for routing configuration.

# Queue names should describe workload characteristics rather than individual
# functions. Common examples include:

# - ``default`` for short general-purpose tasks,
# - ``io-bound`` for external I/O workflows,
# - ``cpu-bound`` for isolated compute workloads,
# - ``scheduled`` for periodic maintenance jobs,
# - domain-specific queues only when operational isolation is required.

# Avoid creating one queue per task. Excessive queue counts increase deployment,
# monitoring, capacity-planning, and broker-management complexity.

# This module must not:

# - contain business logic,
# - import task implementations,
# - connect to the message broker,
# - initialize Celery workers,
# - or create database resources.
# """

# from __future__ import annotations

# from dataclasses import dataclass
# from typing import (
#     Final,
#     TypeAlias,
# )

# from kombu import (
#     Exchange,
#     Queue,
# )

# # =============================================================================
# # ROUTING TYPES
# # =============================================================================

# TaskRoute: TypeAlias = dict[str, str]
# TaskRoutes: TypeAlias = dict[str, TaskRoute]


# # =============================================================================
# # EXCHANGE AND QUEUE DEFAULTS
# # =============================================================================

# DEFAULT_EXCHANGE_NAME: Final[str] = "application"
# DEFAULT_EXCHANGE_TYPE: Final[str] = "direct"

# DEFAULT_QUEUE_NAME: Final[str] = "default"

# PERSISTENT_DELIVERY_MODE: Final[int] = 2


# @dataclass(
#     frozen=True,
#     slots=True,
# )
# class QueueDefinition:
#     """
#     Declarative worker queue definition.

#     Queue declarations remain independent from Kombu so they can be validated
#     without constructing broker-specific objects.

#     Attributes:
#         name: Queue name.
#         routing_key: Routing key used to deliver tasks to the queue. When
#             omitted, the queue name is used.
#         durable: Whether queue metadata survives broker restarts.
#         auto_delete: Whether the broker removes the queue after the final
#             consumer disconnects.
#         exclusive: Whether the queue is restricted to one connection.
#         delivery_mode: Message delivery mode. ``2`` requests persistent
#             messages from supported brokers.
#         queue_arguments: Optional broker-specific queue arguments.
#     """

#     name: str
#     routing_key: str | None = None

#     durable: bool = True
#     auto_delete: bool = False
#     exclusive: bool = False

#     delivery_mode: int = PERSISTENT_DELIVERY_MODE

#     queue_arguments: dict[str, object] | None = None

#     def __post_init__(self) -> None:
#         """
#         Validate the queue declaration.

#         Raises:
#             ValueError: If the queue name, routing key, delivery mode, or queue
#                 arguments are invalid.
#         """

#         normalized_name = self.name.strip()

#         if not normalized_name:
#             raise ValueError(
#                 "Queue name must not be blank"
#             )

#         if normalized_name != self.name:
#             raise ValueError(
#                 "Queue name must not contain surrounding whitespace"
#             )

#         if (
#             self.routing_key is not None
#             and not self.routing_key.strip()
#         ):
#             raise ValueError(
#                 f"Queue '{self.name}' routing key must not be blank"
#             )

#         if (
#             self.routing_key is not None
#             and self.routing_key.strip() != self.routing_key
#         ):
#             raise ValueError(
#                 f"Queue '{self.name}' routing key must not contain "
#                 "surrounding whitespace"
#             )

#         if self.delivery_mode not in {1, 2}:
#             raise ValueError(
#                 f"Queue '{self.name}' delivery_mode must be 1 or 2"
#             )

#         if (
#             self.queue_arguments is not None
#             and not isinstance(
#                 self.queue_arguments,
#                 dict,
#             )
#         ):
#             raise ValueError(
#                 f"Queue '{self.name}' queue_arguments must be a dictionary"
#             )

#     @property
#     def resolved_routing_key(self) -> str:
#         """
#         Return the queue routing key.

#         Returns:
#             Explicit routing key or the queue name when none is configured.
#         """

#         return (
#             self.routing_key
#             or self.name
#         )


# # =============================================================================
# # QUEUE DEFINITIONS
# # =============================================================================

# QUEUE_DEFINITIONS: Final[
#     tuple[QueueDefinition, ...]
# ] = (
#     QueueDefinition(
#         name=DEFAULT_QUEUE_NAME,
#     ),

#     # -------------------------------------------------------------------------
#     # SCHEDULED TASK QUEUE
#     #
#     # Enable when periodic jobs need operational isolation from API-triggered
#     # background tasks.
#     # -------------------------------------------------------------------------
#     # QueueDefinition(
#     #     name="scheduled",
#     # ),

#     # -------------------------------------------------------------------------
#     # I/O-BOUND TASK QUEUE
#     #
#     # Suitable for external API calls, file processing, object storage, or
#     # other workflows dominated by network or disk waiting.
#     # -------------------------------------------------------------------------
#     # QueueDefinition(
#     #     name="io-bound",
#     # ),

#     # -------------------------------------------------------------------------
#     # CPU-BOUND TASK QUEUE
#     #
#     # Run CPU-intensive work on separately sized workers. Do not mix heavy CPU
#     # tasks with latency-sensitive general tasks.
#     # -------------------------------------------------------------------------
#     # QueueDefinition(
#     #     name="cpu-bound",
#     # ),
# )


# # =============================================================================
# # TASK ROUTES
# # =============================================================================

# TASK_ROUTES: Final[TaskRoutes] = {
#     # Add exact task names or carefully bounded patterns.
#     #
#     # Exact task names are preferred because they make routing deterministic
#     # and prevent unrelated tasks from matching broad wildcard patterns.
#     #
#     # Example:
#     #
#     # "app.worker.tasks.rack_replenishment_task.run": {
#     #     "queue": "scheduled",
#     #     "routing_key": "scheduled",
#     # },
# }


# # =============================================================================
# # QUEUE CONSTRUCTION
# # =============================================================================

# def build_task_queues(
#     *,
#     exchange_name: str = DEFAULT_EXCHANGE_NAME,
#     exchange_type: str = DEFAULT_EXCHANGE_TYPE,
# ) -> tuple[Queue, ...]:
#     """
#     Build Celery/Kombu queue declarations.

#     This function creates in-memory Kombu configuration objects only. It does
#     not connect to the broker or declare exchanges and queues remotely.

#     Args:
#         exchange_name: Exchange shared by application worker queues.
#         exchange_type: Kombu exchange type, such as ``direct`` or ``topic``.

#     Returns:
#         Immutable tuple of configured Kombu queues.

#     Raises:
#         ValueError: If exchange configuration or queue declarations are
#             invalid.
#     """

#     normalized_exchange_name = exchange_name.strip()
#     normalized_exchange_type = exchange_type.strip()

#     if not normalized_exchange_name:
#         raise ValueError(
#             "exchange_name must not be blank"
#         )

#     if not normalized_exchange_type:
#         raise ValueError(
#             "exchange_type must not be blank"
#         )

#     validate_queue_definitions(
#         QUEUE_DEFINITIONS
#     )

#     exchange = Exchange(
#         name=normalized_exchange_name,
#         type=normalized_exchange_type,
#         durable=True,
#         auto_delete=False,
#     )

#     return tuple(
#         Queue(
#             name=definition.name,
#             exchange=exchange,
#             routing_key=(
#                 definition.resolved_routing_key
#             ),
#             durable=definition.durable,
#             auto_delete=definition.auto_delete,
#             exclusive=definition.exclusive,
#             queue_arguments=(
#                 dict(definition.queue_arguments)
#                 if definition.queue_arguments is not None
#                 else None
#             ),
#             message_ttl=None,
#         )
#         for definition in QUEUE_DEFINITIONS
#     )


# # =============================================================================
# # VALIDATION
# # =============================================================================

# def validate_queue_definitions(
#     definitions: tuple[QueueDefinition, ...],
# ) -> None:
#     """
#     Validate all declarative queue definitions.

#     Args:
#         definitions: Queue declarations to validate.

#     Raises:
#         ValueError: If no queues are configured, queue names are duplicated,
#             routing keys are duplicated, or the default queue is missing.
#     """

#     if not definitions:
#         raise ValueError(
#             "At least one worker queue must be configured"
#         )

#     queue_names: set[str] = set()
#     routing_keys: set[str] = set()

#     for definition in definitions:
#         if definition.name in queue_names:
#             raise ValueError(
#                 f"Duplicate queue name: '{definition.name}'"
#             )

#         queue_names.add(
#             definition.name
#         )

#         routing_key = (
#             definition.resolved_routing_key
#         )

#         if routing_key in routing_keys:
#             raise ValueError(
#                 f"Duplicate queue routing key: '{routing_key}'"
#             )

#         routing_keys.add(
#             routing_key
#         )

#     if DEFAULT_QUEUE_NAME not in queue_names:
#         raise ValueError(
#             f"Default queue '{DEFAULT_QUEUE_NAME}' must be declared"
#         )


# def validate_task_routes(
#     routes: TaskRoutes,
#     queues: tuple[Queue, ...],
# ) -> None:
#     """
#     Validate task-to-queue routing configuration.

#     Every route must target a declared queue. Routing keys must match the
#     routing key declared by the selected queue, preventing tasks from being
#     silently published to an unroutable key.

#     Args:
#         routes: Task route mapping.
#         queues: Constructed Kombu queues.

#     Raises:
#         ValueError: If a task name is blank, a route is malformed, a queue is
#             undeclared, or a routing key does not match its queue.
#     """

#     declared_queues = {
#         queue.name: queue
#         for queue in queues
#     }

#     if len(declared_queues) != len(queues):
#         raise ValueError(
#             "Constructed worker queues contain duplicate names"
#         )

#     for task_name, route in routes.items():
#         normalized_task_name = task_name.strip()

#         if not normalized_task_name:
#             raise ValueError(
#                 "Task route name must not be blank"
#             )

#         if normalized_task_name != task_name:
#             raise ValueError(
#                 f"Task route '{task_name}' must not contain "
#                 "surrounding whitespace"
#             )

#         if not isinstance(route, dict):
#             raise ValueError(
#                 f"Task route '{task_name}' must be a dictionary"
#             )

#         unsupported_keys = (
#             set(route)
#             - {
#                 "queue",
#                 "routing_key",
#                 "exchange",
#             }
#         )

#         if unsupported_keys:
#             raise ValueError(
#                 f"Task route '{task_name}' contains unsupported keys: "
#                 f"{sorted(unsupported_keys)}"
#             )

#         queue_name = str(
#             route.get(
#                 "queue",
#                 "",
#             )
#         ).strip()

#         if not queue_name:
#             raise ValueError(
#                 f"Task route '{task_name}' must define a queue"
#             )

#         queue = declared_queues.get(
#             queue_name
#         )

#         if queue is None:
#             raise ValueError(
#                 f"Task route '{task_name}' targets undeclared "
#                 f"queue '{queue_name}'"
#             )

#         configured_routing_key = route.get(
#             "routing_key"
#         )

#         if configured_routing_key is not None:
#             routing_key = str(
#                 configured_routing_key
#             ).strip()

#             if not routing_key:
#                 raise ValueError(
#                     f"Task route '{task_name}' contains a blank "
#                     "routing key"
#                 )

#             declared_routing_key = str(
#                 queue.routing_key
#                 or queue.name
#             )

#             if routing_key != declared_routing_key:
#                 raise ValueError(
#                     f"Task route '{task_name}' uses routing key "
#                     f"'{routing_key}', but queue '{queue_name}' declares "
#                     f"'{declared_routing_key}'"
#                 )

#         configured_exchange = route.get(
#             "exchange"
#         )

#         if configured_exchange is not None:
#             exchange_name = str(
#                 configured_exchange
#             ).strip()

#             if not exchange_name:
#                 raise ValueError(
#                     f"Task route '{task_name}' contains a blank exchange"
#                 )

#             declared_exchange = str(
#                 queue.exchange.name
#             )

#             if exchange_name != declared_exchange:
#                 raise ValueError(
#                     f"Task route '{task_name}' uses exchange "
#                     f"'{exchange_name}', but queue '{queue_name}' declares "
#                     f"'{declared_exchange}'"
#                 )


# __all__ = [
#     "DEFAULT_EXCHANGE_NAME",
#     "DEFAULT_EXCHANGE_TYPE",
#     "DEFAULT_QUEUE_NAME",
#     "PERSISTENT_DELIVERY_MODE",
#     "QUEUE_DEFINITIONS",
#     "TASK_ROUTES",
#     "QueueDefinition",
#     "TaskRoute",
#     "TaskRoutes",
#     "build_task_queues",
#     "validate_queue_definitions",
#     "validate_task_routes",
# ]
