# -*- coding: utf-8 -*-
from django.test import TestCase
from django.test import Client as HttpClient
from django.contrib.auth import get_user_model
from django.core.management import call_command

from faker import Faker

from core.models import Child, Sleep, Timer
from dashboard.models import SleepSettlingDraft


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
        # Visiting a child's dashboard is remembered, so /dashboard/ returns
        # there instead of listing the children.
        page = self.c.get("/dashboard/")
        self.assertEqual(page.url, "/children/{}/dashboard/".format(child.slug))

        # Without that memory, several children mean the list itself.
        session = self.c.session
        del session["last_child_slug"]
        session.save()
        page = self.c.get("/dashboard/")
        self.assertEqual(page.status_code, 200)

    def test_sleep_settling_draft(self):
        call_command("fake", verbosity=0, children=1, days=1)
        child = Child.objects.first()
        Timer.objects.filter(child=child).delete()
        timer = Timer.objects.create(child=child, name="Nap", user=self.user)

        self.c.post(
            "/children/{}/sleep-timer/{}/settling/".format(child.slug, timer.pk),
            {"settling": "fussy"},
        )
        self.assertEqual(SleepSettlingDraft.objects.filter(timer=timer).count(), 1)

        # Whoever opens the card next sees the choice, on any device.
        page = self.c.get("/children/{}/track/".format(child.slug))
        self.assertEqual(page.context["sleep_settling"], "fussy")

        # And the save page opens with it already chosen.
        page = self.c.get(
            "/children/{}/sleep-timer/{}/note/".format(child.slug, timer.pk)
        )
        self.assertEqual(page.context["form"].initial["settling"], "fussy")

        # Discarding the timer takes the draft with it and records no sleep.
        sleeps = Sleep.objects.filter(child=child).count()
        self.c.post("/children/{}/timer/{}/stop/".format(child.slug, timer.pk))
        self.assertFalse(Timer.objects.filter(pk=timer.pk).exists())
        self.assertEqual(SleepSettlingDraft.objects.count(), 0)
        self.assertEqual(Sleep.objects.filter(child=child).count(), sleeps)

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
