# -*- coding: utf-8 -*-
from django.test import TestCase
from django.test import Client as HttpClient
from django.contrib.auth import get_user_model
from django.core.management import call_command

from faker import Faker

from core.models import Child


class ViewsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super(ViewsTestCase, cls).setUpClass()
        fake = Faker()
        call_command("migrate", verbosity=0)

        cls.c = HttpClient()

        fake_user = fake.simple_profile()
        cls.credentials = {
            "username": fake_user["username"],
            "password": fake.password(),
        }
        cls.user = get_user_model().objects.create_user(
            is_superuser=True, **cls.credentials
        )

        cls.c.login(**cls.credentials)

    def test_dashboard_views(self):
        page = self.c.get("/dashboard/")
        self.assertEqual(page.url, "/welcome/")

        call_command("fake", verbosity=0, children=1, days=1)
        child = Child.objects.first()
        page = self.c.get("/dashboard/")
        self.assertEqual(page.url, "/children/{}/dashboard/".format(child.slug))

        page = self.c.get("/dashboard/")
        self.assertEqual(page.url, "/children/{}/dashboard/".format(child.slug))
        # Test the actual child dashboard (including cards).
        # TODO: Test cards more granularly.
        page = self.c.get("/children/{}/dashboard/".format(child.slug))
        self.assertEqual(page.status_code, 200)

        Child.objects.create(
            first_name="Second", last_name="Child", birth_date="2000-01-01"
        )
        page = self.c.get("/dashboard/")
        self.assertEqual(page.status_code, 200)

    def test_ai_export_views(self):
        call_command("fake", verbosity=0, children=1, days=2)
        child = Child.objects.first()

        page = self.c.get("/ai-export/")
        self.assertEqual(page.url, "/children/{}/ai-export/".format(child.slug))

        page = self.c.get("/children/{}/ai-export/".format(child.slug))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["days"], 14)
        text = page.context["text"]
        self.assertIn("# Baby Buddy log: {}".format(child.first_name), text)
        self.assertIn("## Daily summary", text)
        self.assertIn("## Log", text)

        page = self.c.get("/children/{}/ai-export/?days=3".format(child.slug))
        self.assertEqual(page.context["days"], 3)
        page = self.c.get("/children/{}/ai-export/?days=abc".format(child.slug))
        self.assertEqual(page.context["days"], 14)
