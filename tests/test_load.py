from locust import HttpUser, task, between
import random

class TaskUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        self.username = f'user_{random.randint(1, 1000000)}'
        self.password = 'pass123'

        register_response = self.client.post(
            '/register',
            params={'username': self.username, 'password': self.password}
        )

        if register_response.status_code != 200:
            self.environment.runner.quit()
            return

        response = self.client.post('/token', data={'username': self.username, 'password': self.password})

        if response.status_code == 200:
            self.token = response.json()['access_token']
            self.headers = {'Authorization': f'Bearer {self.token}'}
        else:
            self.token = None
            self.headers = {}
            self.environment.runner.quit()

    @task(3)
    def create_task(self):
        if self.token:
            self.client.post('/tasks', params={'title': f'Task_{random.randint(1, 10000)}'}, headers=self.headers)

    @task(2)
    def get_tasks(self):
        if self.token:
            self.client.get('/tasks', headers=self.headers)

    @task(1)
    def get_top_tasks(self):
        if self.token:
            self.client.get('/tasks/top/5', headers=self.headers)