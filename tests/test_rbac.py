from __future__ import annotations

import unittest

from src.auth import rbac


class RbacTests(unittest.TestCase):
    def test_all_roles_have_expected_pages(self):
        self.assertEqual(
            rbac.allowed_pages("Super Admin"),
            ["Overview", "Employee Management", "Project Management", "Performance Reviews", "Analytics Dashboard", "User Access Management"],
        )
        self.assertEqual(
            rbac.allowed_pages("HR Admin"),
            ["Overview", "Employee Management", "Performance Reviews", "Analytics Dashboard"],
        )
        self.assertEqual(
            rbac.allowed_pages("Department Manager", "Operations"),
            ["Overview", "Employee Management", "Project Management", "Performance Reviews", "Analytics Dashboard"],
        )
        self.assertEqual(
            rbac.allowed_pages("Analyst"),
            ["Overview", "Project Management", "Analytics Dashboard"],
        )
        self.assertEqual(
            rbac.allowed_pages("Employee"),
            ["Overview", "Performance Reviews"],
        )

    def test_department_manager_is_scoped_and_can_manage_projects(self):
        user = {"role": "Department Manager", "department_id": 3, "department_name": "Operations"}
        self.assertEqual(rbac.scoped_department_id(user), 3)
        self.assertTrue(rbac.can_manage_projects(user))
        self.assertFalse(rbac.can_edit_dept_and_role(user))

    def test_analyst_is_read_only_for_projects(self):
        user = {"role": "Analyst", "department_id": 3}
        self.assertIsNone(rbac.scoped_department_id(user))
        self.assertFalse(rbac.can_manage_projects(user))
        self.assertFalse(rbac.can(user["role"], "project.create"))

    def test_employee_has_personal_review_access_only(self):
        user = {"role": "Employee", "department_id": 3}
        self.assertEqual(rbac.allowed_pages(user["role"]), ["Overview", "Performance Reviews"])
        self.assertFalse(rbac.can(user["role"], "review.create"))
        self.assertFalse(rbac.can(user["role"], "review.update"))


if __name__ == "__main__":
    unittest.main()