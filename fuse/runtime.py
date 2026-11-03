"""
fuse/runtime.py
===============
Singleton RuntimeManager that owns every active Fuse workflow execution.

Webhook, schedule, Webex, and GitHub workflows persist their compiled graph in
Firestore; triggers resolve lazily via ``resolve_execution()`` after restart.
Schedule firing is delegated to Cron Service (cron-job.org → cron-service → noney webhook).
"""

import logging
import secrets
import threading

logger = logging.getLogger(__name__)


class WebhookExecution:
    def __init__(self, workflow_id: str, compiled_graph: dict) -> None:
        self.workflow_id = workflow_id
        self.compiled_graph = compiled_graph

    def start(self) -> None:
        logger.info("[FUSE] Webhook workflow '%s' is now active.", self.workflow_id)

    def stop(self) -> None:
        logger.info("[FUSE] Webhook workflow '%s' deactivated.", self.workflow_id)


class ScheduleExecution:
    """
    Active schedule workflow — registers with Cron Service on start, removes on stop.
    """

    def __init__(self, workflow_id: str, compiled_graph: dict) -> None:
        self.workflow_id = workflow_id
        self.compiled_graph = compiled_graph

    def start(self) -> None:
        from db import db
        from utils.cron_service import is_cron_service_configured, upsert_workflow_schedule

        if not is_cron_service_configured():
            raise RuntimeError(
                "Cron service is not configured (CRON_SERVICE_HOST / CRON_SERVICE_API_KEY)."
            )

        owner_id = self.compiled_graph.get("owner_id", "")
        starter_config = dict(self.compiled_graph["starter"].get("config") or {})

        existing = self.compiled_graph.get("cron_schedule") or {}
        secret = existing.get("secret") or secrets.token_urlsafe(32)

        workflow_doc = db.workflow.get(self.workflow_id, owner_id) if owner_id else None
        workflow_name = (workflow_doc or {}).get("name") or ""
        owner_email = db.user.get_email(owner_id) if owner_id else None

        base = self._webhook_base_url()
        noney_trigger_url = f"{base}/fuse/schedule/webhook/{self.workflow_id}"

        result = upsert_workflow_schedule(
            {
                "workflow_id": self.workflow_id,
                "workflow_name": workflow_name,
                "owner_id": owner_id,
                "owner_email": owner_email or "",
                "schedule_config": starter_config,
                "timezone": starter_config.get("timezone") or "UTC",
                "noney_trigger_url": noney_trigger_url,
                "noney_trigger_secret": secret,
            }
        )
        if not result:
            raise RuntimeError("Failed to register schedule with Cron Service.")

        self.compiled_graph["cron_schedule"] = {
            "secret": secret,
            "cron_org_job_id": result.get("cron_org_job_id"),
            "public_webhook_url": result.get("public_webhook_url"),
        }
        logger.info(
            "[FUSE] Schedule workflow '%s' registered (cron-job.org id=%s).",
            self.workflow_id,
            result.get("cron_org_job_id"),
        )

    def stop(self) -> None:
        from utils.integrations.cron_schedule_utils import cleanup_cron_schedule_workflow

        cleanup_cron_schedule_workflow(self.workflow_id)
        self.compiled_graph.pop("cron_schedule", None)
        logger.info("[FUSE] Schedule workflow '%s' deactivated.", self.workflow_id)

    @staticmethod
    def _webhook_base_url() -> str:
        from config import CONFIG

        return CONFIG.HOST.rstrip("/")


class GithubPullRequestExecution:
    def __init__(self, workflow_id: str, compiled_graph: dict) -> None:
        self.workflow_id = workflow_id
        self.compiled_graph = compiled_graph

    def start(self) -> None:
        from utils.integrations.github_utils import (
            create_github_webhook,
            delete_github_webhook,
            get_github_access_token,
        )

        existing = self.compiled_graph.get("github_webhook") or {}
        if existing.get("id") and existing.get("secret"):
            logger.info(
                "[FUSE] Github PR workflow '%s' restored (existing webhook=%s).",
                self.workflow_id,
                existing["id"],
            )
            return

        owner_id = self.compiled_graph.get("owner_id", "")
        starter_config = self.compiled_graph["starter"].get("config", {})

        access_token = get_github_access_token(owner_id)
        if not access_token:
            raise RuntimeError("Github integration is not configured or token refresh failed.")

        base = self._webhook_base_url()
        target_url = f"{base}/fuse/github/webhook/{self.workflow_id}"

        repo_name = starter_config.get("repo_name", "").strip()
        if not repo_name:
            raise RuntimeError("Repository name is required for GitHub PR Trigger.")

        webhook_id = None
        try:
            webhook = create_github_webhook(
                access_token,
                repo_name=repo_name,
                target_url=target_url,
            )
            webhook_id = webhook["id"]
            self.compiled_graph["github_webhook"] = {
                "id": webhook_id,
                "secret": webhook["secret"],
                "repo_name": repo_name,
            }
        except Exception:
            if webhook_id:
                delete_github_webhook(access_token, repo_name, webhook_id)
            raise

        logger.info(
            "[FUSE] Github PR workflow '%s' is now active (webhook=%s).",
            self.workflow_id,
            webhook_id,
        )

    def stop(self) -> None:
        from utils.integrations.github_utils import cleanup_github_workflow_webhook

        owner_id = self.compiled_graph.get("owner_id", "")
        cleanup_github_workflow_webhook(owner_id, self.compiled_graph)
        self.compiled_graph.pop("github_webhook", None)
        logger.info("[FUSE] Github PR workflow '%s' deactivated.", self.workflow_id)

    @staticmethod
    def _webhook_base_url() -> str:
        from config import CONFIG

        return CONFIG.HOST.rstrip("/")


class WebexMessageExecution:
    def __init__(self, workflow_id: str, compiled_graph: dict) -> None:
        self.workflow_id = workflow_id
        self.compiled_graph = compiled_graph

    def start(self) -> None:
        from utils.integrations.webex_utils import (
            build_webex_message_filter,
            create_message_webhook,
            delete_webhook,
            delete_webhooks_for_target_url,
            get_webex_access_token,
        )

        owner_id = self.compiled_graph.get("owner_id", "")
        starter_config = self.compiled_graph["starter"].get("config", {})

        access_token = get_webex_access_token(owner_id)
        if not access_token:
            raise RuntimeError("Webex integration is not configured or token refresh failed.")

        base = self._webhook_base_url()
        target_url = f"{base}/fuse/webex/webhook/{self.workflow_id}"
        filter_str = build_webex_message_filter(starter_config)

        existing = self.compiled_graph.get("webex_webhook") or {}
        if existing.get("id") and existing.get("secret"):
            delete_webhooks_for_target_url(
                access_token,
                target_url,
                keep_id=existing["id"],
            )
            logger.info(
                "[FUSE] Webex message workflow '%s' restored (existing webhook=%s).",
                self.workflow_id,
                existing["id"],
            )
            return

        delete_webhooks_for_target_url(access_token, target_url)

        webhook_id = None
        try:
            webhook = create_message_webhook(
                access_token,
                target_url=target_url,
                name=f"Fuse workflow {self.workflow_id}",
                filter_str=filter_str,
            )
            webhook_id = webhook["id"]
            self.compiled_graph["webex_webhook"] = {
                "id": webhook_id,
                "secret": webhook["secret"],
            }
        except Exception:
            if webhook_id:
                delete_webhook(access_token, webhook_id)
            raise

        logger.info(
            "[FUSE] Webex message workflow '%s' is now active (webhook=%s).",
            self.workflow_id,
            webhook_id,
        )

    def stop(self) -> None:
        from utils.integrations.webex_utils import cleanup_webex_workflow_webhook

        owner_id = self.compiled_graph.get("owner_id", "")
        cleanup_webex_workflow_webhook(owner_id, self.compiled_graph)
        self.compiled_graph.pop("webex_webhook", None)
        logger.info("[FUSE] Webex message workflow '%s' deactivated.", self.workflow_id)

    @staticmethod
    def _webhook_base_url() -> str:
        from config import CONFIG

        return CONFIG.HOST.rstrip("/")


class RuntimeManager:
    _instance: "RuntimeManager | None" = None
    _class_lock = threading.Lock()

    def __new__(cls) -> "RuntimeManager":
        with cls._class_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._active: dict[
                    str,
                    WebhookExecution
                    | ScheduleExecution
                    | WebexMessageExecution
                    | GithubPullRequestExecution,
                ] = {}
                inst._active_lock = threading.Lock()
                cls._instance = inst
        return cls._instance

    def activate(self, workflow_id: str, compiled_graph: dict) -> None:
        self.deactivate(workflow_id)

        starter_type = compiled_graph["starter"]["node_type"]

        if starter_type == "webhook":
            execution = WebhookExecution(workflow_id, compiled_graph)
        elif starter_type == "webex_message":
            execution = WebexMessageExecution(workflow_id, compiled_graph)
        elif starter_type == "github_pull_request":
            execution = GithubPullRequestExecution(workflow_id, compiled_graph)
        elif starter_type == "schedule":
            execution = ScheduleExecution(workflow_id, compiled_graph)
        else:
            raise ValueError(f"Unknown starter node type: '{starter_type}'")

        execution.start()

        with self._active_lock:
            self._active[workflow_id] = execution

    def deactivate(self, workflow_id: str) -> None:
        with self._active_lock:
            execution = self._active.pop(workflow_id, None)
        if execution is not None:
            execution.stop()

    def get_execution(
        self, workflow_id: str
    ) -> (
        WebhookExecution
        | ScheduleExecution
        | WebexMessageExecution
        | GithubPullRequestExecution
        | None
    ):
        with self._active_lock:
            return self._active.get(workflow_id)

    def resolve_execution(
        self, workflow_id: str
    ) -> (
        WebhookExecution
        | ScheduleExecution
        | WebexMessageExecution
        | GithubPullRequestExecution
        | None
    ):
        execution = self.get_execution(workflow_id)
        if execution is not None:
            return execution

        from db import db

        workflow = db.workflow.get_active_by_id(workflow_id)
        if workflow is None:
            return None

        from fuse.workflow_graph import load_execution_graph_for_workflow

        compiled_graph = load_execution_graph_for_workflow(workflow)
        if not compiled_graph:
            logger.warning(
                "[FUSE] Active workflow '%s' has no version/graph — cannot resolve.",
                workflow_id,
            )
            return None

        starter_type = (
            workflow.get("starter_type")
            or compiled_graph.get("starter", {}).get("node_type", "")
        )

        fuse_runtime = workflow.get("fuse_runtime") or {}
        for key in ("webex_webhook", "github_webhook", "cron_schedule"):
            if fuse_runtime.get(key):
                compiled_graph[key] = fuse_runtime[key]

        try:
            if starter_type == "schedule":
                execution = ScheduleExecution(workflow_id, compiled_graph)
                with self._active_lock:
                    self._active[workflow_id] = execution
            else:
                self.activate(workflow_id, compiled_graph)
            logger.info(
                "[FUSE] Lazy-loaded active workflow '%s' from Firestore (starter=%s).",
                workflow_id,
                starter_type,
            )
        except Exception:
            logger.exception(
                "[FUSE] Failed to lazy-load workflow '%s' from Firestore.", workflow_id
            )
            return None

        return self.get_execution(workflow_id)

    def is_active(self, workflow_id: str) -> bool:
        with self._active_lock:
            return workflow_id in self._active

    def resync_schedules(self, active_workflows: list) -> None:
        """Re-upsert active schedule workflows with Cron Service after deploy."""
        from fuse.workflow_graph import load_execution_graph_for_workflow

        for wf in active_workflows:
            workflow_id = wf.get("id", "")
            compiled_graph = load_execution_graph_for_workflow(wf)
            if not compiled_graph:
                continue
            if (
                wf.get("starter_type")
                or compiled_graph.get("starter", {}).get("node_type", "")
            ) != "schedule":
                continue
            try:
                self.activate(workflow_id, compiled_graph)
                logger.info("[FUSE] Re-synced schedule workflow '%s' with Cron Service.", workflow_id)
            except Exception:
                logger.exception(
                    "[FUSE] Failed to re-sync schedule '%s' on startup.", workflow_id
                )

    def shutdown(self) -> None:
        with self._active_lock:
            for execution in self._active.values():
                execution.stop()
            self._active.clear()


runtime = RuntimeManager()
