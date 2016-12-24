"""
pynpuzzle - Solve n-puzzle with Python

Uniform-cost search algorithm

Version : 1.0.0
Author : Hamidreza Mahdavipanah
Repository: http://github.com/mahdavipanah/pynpuzzle
License : MIT License
"""
from .util import best_first_seach as bfs


def search(state, goal_state):
    """Uniform-cost search"""

    def gn(node):
        return node.gn()

    return bfs.search(state, goal_state, gn)
