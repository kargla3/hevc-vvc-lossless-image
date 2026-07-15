import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils
import pytest


@pytest.mark.parametrize("order_fn", [utils.raster_order, utils.hilbert_order, utils.zorder_order])
@pytest.mark.parametrize("rows,cols", [(1, 1), (3, 5), (4, 4), (7, 2), (16, 24)])
def test_order_is_permutation(order_fn, rows, cols):
	order = order_fn(rows, cols)
	assert sorted(order) == list(range(rows * cols))


def test_reorder_unreorder_roundtrip():
	items = list("abcdefghijkl")  # 3x4
	order = utils.hilbert_order(3, 4)
	seq = utils.reorder(items, order)
	restored = utils.unreorder(seq, order)
	assert restored == items
