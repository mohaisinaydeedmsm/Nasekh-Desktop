import os
import sys
import time
import tempfile
from PySide6.QtCore import QCoreApplication

from core.utils import Task, TaskStatus
from core.task_worker import TaskWorker

def test_task_worker():
    print("=" * 60)
    print("THAFREEG SUITE - TASK WORKER THREAD-SAFETY TEST")
    print("=" * 60)

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    received_logs = []
    received_progress = []
    received_finished = []
    received_failed = []

    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.txt', encoding='utf-8') as f:
        temp_out = f.name

    try:
        # 1. Test Dummy Success Workflow
        task_data = {
            "api_keys": ["gsk_test"],
            "entries": [],
            "output_path": temp_out,
            "append": False,
            "config": {"export_docx": False, "export_md": False}
        }
        task = Task("worker_test_101", "LOCAL", "Worker Thread Test", task_data)

        worker = TaskWorker(task)

        worker.log_added.connect(lambda t_id, msg: received_logs.append((t_id, msg)))
        worker.progress_changed.connect(lambda t_id, p, eta: received_progress.append((t_id, p, eta)))
        worker.task_finished.connect(lambda t_id, stats: received_finished.append((t_id, stats)))
        worker.task_failed.connect(lambda t_id, err: received_failed.append((t_id, err)))

        print("\n[1/2] Launching TaskWorker in QThread...")
        worker.start()
        
        # Process event loop briefly until thread finishes
        timeout = 10.0
        start_t = time.time()
        while worker.isRunning() and (time.time() - start_t) < timeout:
            app.processEvents()
            time.sleep(0.02)

        worker.wait()
        app.processEvents()

        assert len(received_finished) == 1, f"TaskWorker did not emit task_finished signal. Failed signals: {received_failed}"
        assert received_finished[0][0] == "worker_test_101", "Task ID mismatch in signal"
        print(f"  [OK] TaskWorker finished cleanly. Task Status: {task.status}")
        print(f"  [OK] Captured {len(received_logs)} log signals and {len(received_progress)} progress signals.")

        # 2. Test Exception Handling Workflow
        print("\n[2/2] Testing Exception Safety with invalid Task Type...")
        invalid_task = Task("worker_test_102", "INVALID_TYPE", "Invalid Task", task_data)
        fail_worker = TaskWorker(invalid_task)

        fail_logs = []
        fail_signals = []
        fail_worker.log_added.connect(lambda t_id, msg: fail_logs.append(msg))
        fail_worker.task_failed.connect(lambda t_id, err: fail_signals.append((t_id, err)))

        fail_worker.start()
        start_t = time.time()
        while fail_worker.isRunning() and (time.time() - start_t) < timeout:
            app.processEvents()
            time.sleep(0.02)

        fail_worker.wait()
        app.processEvents()

        assert len(fail_signals) == 1, "TaskWorker did not emit task_failed on exception"
        assert "Unknown task type" in fail_signals[0][1], "Error message mismatch"
        assert invalid_task.status == TaskStatus.FAILED, "Task status was not set to FAILED"
        print(f"  [OK] Exception handled safely. Exception: '{fail_signals[0][1]}'")
        print(f"  [OK] Task Status: {invalid_task.status}")

        print("\n" + "=" * 60)
        print("TASK WORKER THREAD-SAFETY & SIGNAL TESTS PASSED SUCCESSFULLY!")
        print("=" * 60)
        return True
    finally:
        if os.path.exists(temp_out):
            os.remove(temp_out)

if __name__ == "__main__":
    success = test_task_worker()
    sys.exit(0 if success else 1)
