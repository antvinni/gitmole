import unittest

from gitmole import coupling


def pair(a, b, degree=100, revs=10):
    return {"entity": a, "coupled": b, "degree": degree, "average-revs": revs}


def clique(directory, names, degree=100, revs=10):
    files = [f"{directory}/{n}" if directory else n for n in names]
    return [pair(a, b, degree, revs) for i, a in enumerate(files) for b in files[i + 1:]]


class Clusters(unittest.TestCase):
    def test_a_directory_of_four_or_more_files_becomes_one_cluster(self):
        pairs = clique("rich/_unicode_data", ["u10.py", "u11.py", "u12.py", "u13.py"]) + [pair("a.py", "b.py", 90)]
        groups, rest = coupling.clusters(pairs)
        self.assertEqual(groups, [{"dir": "rich/_unicode_data/", "files": 4, "pairs": 6, "degree": 100, "average-revs": 10}])
        self.assertEqual(rest, [pair("a.py", "b.py", 90)])

    def test_the_cluster_degree_is_the_weakest_pair(self):
        pairs = clique("d", ["a", "b", "c", "e"], degree=100)
        pairs[2]["degree"] = 83
        pairs[4]["average-revs"] = 40
        [g], _ = coupling.clusters(pairs)
        self.assertEqual(g["degree"], 83)
        self.assertEqual(g["average-revs"], 15)   # the mean of the pairs' averages, rounded

    def test_three_files_stay_as_pairs(self):
        pairs = clique("d", ["a", "b", "c"])
        groups, rest = coupling.clusters(pairs)
        self.assertEqual(groups, [])
        self.assertEqual(rest, pairs)

    def test_pairs_across_directories_never_cluster(self):
        pairs = [pair("x/a", "y/b"), pair("x/c", "y/d"), pair("x/e", "y/f"), pair("x/g", "y/h")]
        groups, rest = coupling.clusters(pairs)
        self.assertEqual(groups, [])
        self.assertEqual(len(rest), 4)

    def test_root_files_cluster_under_their_own_label_and_largest_cluster_first(self):
        pairs = clique("", ["a", "b", "c", "d"]) + clique("lib", ["p", "q", "r", "s", "t"], degree=90)
        groups, rest = coupling.clusters(pairs)
        self.assertEqual([g["dir"] for g in groups], ["lib/", "(root files)"])
        self.assertEqual(rest, [])

    def test_a_chain_is_not_a_cluster(self):
        pairs = [pair("d/a", "d/b"), pair("d/b", "d/c"), pair("d/c", "d/e")]   # 4 files, 3 of 6 possible pairs: connected, not a clique
        groups, rest = coupling.clusters(pairs)
        self.assertEqual(groups, [])
        self.assertEqual(rest, pairs)

    def test_a_near_complete_clique_is_a_cluster(self):
        pairs = clique("d", ["a", "b", "c", "e", "f"])   # 5 files, 10 pairs
        eight = pairs[:8]
        [g], rest = coupling.clusters(eight)
        self.assertEqual((g["files"], g["pairs"]), (5, 8))
        self.assertEqual(rest, [])
        groups, rest = coupling.clusters(pairs[:7])   # 7 of 10 is under the 80% floor
        self.assertEqual(groups, [])
        self.assertEqual(len(rest), 7)

    def test_two_unrelated_pairs_in_one_directory_are_not_a_cluster(self):
        pairs = [pair("a", "b"), pair("c", "d")]
        groups, rest = coupling.clusters(pairs)
        self.assertEqual(groups, [])
        self.assertEqual(rest, pairs)
