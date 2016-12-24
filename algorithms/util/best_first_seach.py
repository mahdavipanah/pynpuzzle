"""
pynpuzzle - Solve n-puzzle with Python

Best-first search algorithm

Version : 1.0.0
Author : Hamidreza Mahdavipanah
Repository: http://github.com/mahdavipanah/pynpuzzle
License : MIT License
"""
import heapq
from .tree_search import Node


def search(state, goal_state, fn):
    """Best-first search"""
    queue = []
    entrance = 0
    node = Node(state)
    while not node.is_goal(goal_state):
        node.expand()
        for child in node.children:
            queue_item = (fn(child), entrance, child)
            heapq.heappush(queue, queue_item)
            entrance += 1
        node = heapq.heappop(queue)[2]

    output = []
    output.append(node.state)
    for parent in node.parents():
        output.append(parent.state)
    output.reverse()

    return output
