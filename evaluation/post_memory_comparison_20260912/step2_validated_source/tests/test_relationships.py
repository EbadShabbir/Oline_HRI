"""Behavioral examples for the bounded named-relationship coverage check."""

import unittest

from oline_hri.relationships import missing_user_relationship


class UserRelationshipCoverageTests(unittest.TestCase):
    def test_direct_appositional_and_coordinated_paraphrases_preserve_fact(
        self,
    ) -> None:
        canonical = "Theo is the user's fictional robotics project partner."
        speeches = (
            "Theo is your robotics project partner.",
            "Yes, Theo is your robotics project partner.",
            "Based on that memory, Theo is your robotics project partner.",
            "Meet Theo, your robotics project partner, Tuesday mornings.",
            "Theo, your partner on the robotics project, can help.",
            "Meet your robotics-project partner Theo.",
            "Meet your robotics project partner, Theo, Tuesday mornings.",
            "Theo, as your robotics project partner, can help.",
            "Your partner for the robotics project is Theo.",
            "Plan with Theo (your partner on the robotics project).",
            "Theo, who is your partner for your robotics project, can help.",
            "Meet Theo—your robotics-project partner—Tuesday mornings.",
            "You and Theo are robotics project partners.",
            "Theo and you are partners on the robotics project.",
            "Your robotics project partner is theo.",
        )
        for speech in speeches:
            with self.subTest(speech=speech):
                self.assertFalse(missing_user_relationship(canonical, speech))

    def test_name_role_and_each_domain_qualifier_must_be_linked(self) -> None:
        canonical = "Theo is the user's robotics project partner."
        speeches = (
            "Meet Theo Tuesday mornings.",
            "Theo is your partner.",
            "Theo is your robotics partner.",
            "Theo is your project partner.",
            "Theo is your partner. Review the robotics project.",
            "Theo, your partner, reviews the robotics project.",
            "Theo joins your robotics project. Your partner will help.",
            "Theo is your colleague; Alice is your robotics project partner.",
            "Theo, your robotics project partner is Alice.",
            "Theo, your partner on the robotics project is Alice.",
            "Theo, your robotics project partner Alice can help.",
            "Meet Theo and your robotics project partner Alice.",
            "Your robotics project partner Alice can meet Theo.",
            "Theo is Alice's robotics project partner.",
            "Theo is your friend's robotics project partner.",
            "Theo is your robotics project partner's friend.",
            "Theo is my robotics project partner.",
            "Theo is the user's robotics project partner.",
        )
        for speech in speeches:
            with self.subTest(speech=speech):
                self.assertTrue(missing_user_relationship(canonical, speech))

    def test_negative_uncertain_and_third_party_sources_add_no_positive_fact(
        self,
    ) -> None:
        sources = (
            "Theo is not the user's robotics project partner.",
            "Theo isn't the user's robotics project partner.",
            "Theo isn’t the user's robotics project partner.",
            "Theo is no longer the user's robotics project partner.",
            "Theo may be the user's robotics project partner.",
            "Theo might be the user's robotics project partner.",
            "Maybe Theo is the user's robotics project partner.",
            "Perhaps Theo is the user's robotics project partner.",
            "If Theo is the user's robotics project partner, ask him.",
            "I don't think Theo is the user's robotics project partner.",
            "It is unclear whether Theo is the user's project partner.",
            "Theo is the user's possible project partner.",
            "Theo is the user's project partner?",
            "Theo is Alice's robotics project partner.",
            "Theo is her robotics project partner.",
            "Theo is the user's mother's robotics project partner.",
            "Theo is your friend Alice's robotics project partner.",
            "The user likes robotics project meetings.",
        )
        for canonical in sources:
            with self.subTest(canonical=canonical):
                self.assertFalse(
                    missing_user_relationship(canonical, "No stated role.")
                )

    def test_negative_or_uncertain_response_does_not_cover_positive_source(
        self,
    ) -> None:
        canonical = "Theo is your robotics project partner."
        speeches = (
            "Theo is not your robotics project partner.",
            "Theo isn't your robotics project partner.",
            "Theo isn’t your robotics project partner.",
            "Your robotics project partner is not Theo.",
            "Not your robotics project partner Theo.",
            "Maybe Theo is your robotics project partner.",
            "I don't think Theo is your robotics project partner.",
            "Theo might be your robotics project partner.",
            "Theo is your possible robotics project partner.",
            "Theo is your robotics project partner?",
        )
        for speech in speeches:
            with self.subTest(speech=speech):
                self.assertTrue(missing_user_relationship(canonical, speech))

    def test_stored_user_wording_variants_create_the_same_requirement(
        self,
    ) -> None:
        sources = (
            "Nina is the user's older sister.",
            "Nina is the user’s older sister.",
            "Nina is User's older sister.",
            "Nina is my older sister.",
            "Nina is your older sister.",
            "Nina, your older sister, lives nearby.",
            "Your older sister is Nina.",
        )
        for canonical in sources:
            with self.subTest(canonical=canonical):
                self.assertFalse(
                    missing_user_relationship(
                        canonical, "Nina is your older sister."
                    )
                )
                self.assertTrue(
                    missing_user_relationship(canonical, "Nina is your sister.")
                )

    def test_generic_names_roles_and_projects_remain_bound(self) -> None:
        canonical = (
            "Nina is your garden project partner. "
            "Maya is your chess club teammate."
        )
        self.assertFalse(
            missing_user_relationship(
                canonical,
                "Nina, your partner on the garden project, can meet Maya, "
                "your chess club teammate.",
            )
        )
        for speech in (
            "Nina is your chess club teammate. Maya is your garden project "
            "partner.",
            "Nina is your garden project teammate. Maya is your chess club "
            "partner.",
            "Nina is your partner. Maya is your garden project and chess "
            "club teammate.",
        ):
            with self.subTest(speech=speech):
                self.assertTrue(missing_user_relationship(canonical, speech))

    def test_post_role_source_qualifiers_and_coordinated_sources(self) -> None:
        for canonical in (
            "Maya is the user's partner on the garden project.",
            "The user and Maya are garden project partners.",
            "Maya and the user are partners for the garden project.",
        ):
            with self.subTest(canonical=canonical):
                self.assertFalse(
                    missing_user_relationship(
                        canonical, "Maya is your garden project partner."
                    )
                )
                self.assertTrue(
                    missing_user_relationship(canonical, "Maya is your partner.")
                )


if __name__ == "__main__":
    unittest.main()
