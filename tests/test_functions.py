import luigi

def run_luigi_worker(task):
    w = luigi.worker.Worker()
    w.add(task)
    status = w.run()

    return status