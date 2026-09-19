# v0.2.16
# {
#   "Seq": [
#     { "Depends": "py-lib-genlayer-embeddings:09h0i209wrzh4xzq86f79c60x0ifs7xcjwl53ysrnw06i54ddxyi" },
#     { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
#   ]
# }
import numpy as np
from genlayer import *
import genlayer_embeddings as gle
import datetime
import typing
from dataclasses import dataclass

@allow_storage
@dataclass
class WorkerProfile:
    worker_address: Address
    skill_text: str

@gl.evm.contract_interface
class _Recipient:
    class View:
        pass
    class Write:
        pass

class TaskMatchEscrow(gl.Contract):
    skill_registry: gle.VecDB[np.float32, typing.Literal[384], WorkerProfile]
    total_workers: u256

    is_open: bool
    task_description: str
    poster: Address
    assigned_worker: Address
    reward: u256
    deliverable_url: str
    deadline: datetime.datetime
    total_completed: u256
    last_result: str

    def __init__(self):
        self.total_workers = u256(0)
        self.is_open = False
        self.reward = u256(0)
        self.total_completed = u256(0)
        self.last_result = "No tasks completed yet."

    def get_embedding_generator(self):
        return gle.SentenceTransformer("all-MiniLM-L6-v2")

    def get_embedding(
        self, txt: str
    ) -> np.ndarray[tuple[typing.Literal[384]], np.dtypes.Float32DType]:
        return self.get_embedding_generator()(txt)

    @gl.public.write
    def register_skill(self, skill_description: str) -> None:
        emb = self.get_embedding(skill_description)
        profile = WorkerProfile(worker_address=gl.message.sender_address, skill_text=skill_description)
        self.skill_registry.insert(emb, profile)
        self.total_workers = self.total_workers + u256(1)

    @gl.public.view
    def find_best_match(self, task_desc: str, top_n: int) -> list:
        emb = self.get_embedding(task_desc)
        results = list(self.skill_registry.knn(emb, top_n))
        return [
            {"similarity": str(1 - r.distance), "worker": str(r.value.worker_address), "skill": r.value.skill_text}
            for r in results
        ]

    @gl.public.write.payable
    def post_task(self, task_description: str, worker_address: str) -> None:
        assert not self.is_open, "A task is already open."
        assert gl.message.value > u256(0), "You must fund the task reward."
        self.is_open = True
        self.task_description = task_description
        self.poster = gl.message.sender_address
        self.assigned_worker = Address(worker_address)
        self.reward = gl.message.value
        self.deliverable_url = ""
        self.deadline = datetime.datetime.now() + datetime.timedelta(hours=48)

    @gl.public.write
    def cancel_task(self) -> None:
        assert self.is_open, "No open task."
        assert self.deliverable_url == "", "Cannot cancel after a deliverable was submitted."
        assert gl.message.sender_address == self.poster, "Only the poster can cancel."
        _Recipient(self.poster).emit_transfer(value=self.reward)
        self.is_open = False
        self.reward = u256(0)

    @gl.public.write
    def submit_deliverable(self, url: str) -> None:
        assert self.is_open, "No open task."
        assert gl.message.sender_address == self.assigned_worker, "Only the assigned worker can submit."
        self.deliverable_url = url
        self._judge()

    @gl.public.write
    def claim_timeout_refund(self) -> None:
        assert self.is_open, "No open task."
        assert self.deliverable_url == "", "A deliverable was already submitted."
        assert datetime.datetime.now() >= self.deadline, "Deadline has not passed yet."
        _Recipient(self.poster).emit_transfer(value=self.reward)
        self.is_open = False
        self.reward = u256(0)

    def _judge(self) -> None:
        task = self.task_description
        url = self.deliverable_url

        def nondet_eval() -> str:
            content = gl.nondet.web.render(url, mode="text")
            prompt = (
                "Task requirement: '" + task + "'\n"
                "Submitted deliverable content: '" + content[:3000] + "'\n"
                "Does the deliverable satisfy the task requirement?\n"
                "Respond with EXACTLY one word: SATISFIED or UNSATISFIED"
            )
            raw = gl.nondet.exec_prompt(prompt).strip().upper()
            return "SATISFIED" if "SATISFIED" in raw and "UN" not in raw else "UNSATISFIED"

        verdict = gl.eq_principle.prompt_comparative(
            nondet_eval,
            principle="Equivalent answers agree on the categorical outcome SATISFIED or UNSATISFIED; wording never matters since only this exact token is produced."
        )

        if verdict == "SATISFIED":
            _Recipient(self.assigned_worker).emit_transfer(value=self.reward)
            self.last_result = "SATISFIED - worker paid " + str(self.reward) + " wei"
        else:
            _Recipient(self.poster).emit_transfer(value=self.reward)
            self.last_result = "UNSATISFIED - poster refunded " + str(self.reward) + " wei"

        self.total_completed = self.total_completed + u256(1)
        self.is_open = False
        self.reward = u256(0)

    @gl.public.view
    def get_current_task(self) -> str:
        if not self.is_open:
            return "No task currently open."
        return "Task: " + self.task_description + " | Reward: " + str(self.reward) + " | Worker: " + str(self.assigned_worker)

    @gl.public.view
    def get_last_result(self) -> str:
        return self.last_result

    @gl.public.view
    def get_total_workers(self) -> str:
        return str(self.total_workers)

    @gl.public.view
    def get_total_completed(self) -> str:
        return str(self.total_completed)
