"""
pynpuzzle - Solve n-puzzle with Python

Breadth-first search algorithm

Version : 1.0.0
Author : Hamidreza Mahdavipanah
Repository: http://github.com/mahdavipanah/pynpuzzle
License : MIT License
"""
from .util.tree_search import Node
from collections import deque


def search(state, goal_state):
    """Breadth-first search"""
    queue = deque()
    current_node = Node(state)
    while not current_node.is_goal(goal_state):
        current_node.expand()
        queue.extendleft(current_node.children)
        current_node = queue.pop()

    output = []
    output.append(current_node.state)
    for parent in current_node.parents():
        output.append(parent.state)
    output.reverse()

    return output
