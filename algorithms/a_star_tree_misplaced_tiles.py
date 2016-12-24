"""
pynpuzzle - Solve n-puzzle with Python

A* tree search algorithm using misplaced tiles heuristic

Version : 1.0.0
Author : Hamidreza Mahdavipanah
Repository: http://github.com/mahdavipanah/pynpuzzle
License : MIT License
"""
import heapq
from .util import best_first_seach as bfs


def search(state, goal_state):
    """A* tree search using misplaced tiles heuristic"""

    def gn(node):
        return node.gn()

    tiles_places = []
    for i in range(len(goal_state)):
        for j in range(len(goal_state)):
            heapq.heappush(tiles_places, (goal_state[i][j], (i, j)))

    def hn(node):
        misplace_count = 0
        for i in range(len(node.state)):
            for j in range(len(node.state)):
                if node.state[i][j] == 0:
                    continue
                tile_i, tile_j = tiles_places[node.state[i][j]][1]
                if i != tile_i or j != tile_j:
                    misplace_count += 1
        return misplace_count

    def fn(node):
        return gn(node) + hn(node)

    return bfs.search(state, goal_state, fn)
