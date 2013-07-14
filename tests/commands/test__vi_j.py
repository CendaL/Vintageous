import unittest

from Vintageous.vi.constants import _MODE_INTERNAL_NORMAL
from Vintageous.vi.constants import MODE_NORMAL
from Vintageous.vi.constants import MODE_VISUAL
from Vintageous.vi.constants import MODE_VISUAL_LINE

from Vintageous.tests.commands import set_text
from Vintageous.tests.commands import add_selection
from Vintageous.tests.commands import get_sel
from Vintageous.tests.commands import first_sel
from Vintageous.tests.commands import BufferTest


# TODO: Rename _vi_j_motion.
# TODO: Remove 'extend' param.
# TODO: Ensure that we only create empty selections while testing. Add assert_all_sels_empty()?
class Test_vi_j_InNormalMode(BufferTest):
    def testMoveOne(self):
        set_text(self.view, 'abc\nabc\nabc')
        add_selection(self.view, a=1, b=1)

        self.view.run_command('_vi_j_motion', {'mode': MODE_NORMAL, 'count': 1, 'xpos': 1})

        target = self.view.text_point(1, 1)
        expected = self.R(target, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveMany(self):
        set_text(self.view, ''.join(('abc\n',) * 60))
        add_selection(self.view, a=1, b=1)

        self.view.run_command('_vi_j_motion', {'mode': MODE_NORMAL, 'count': 50, 'xpos': 1})

        target = self.view.text_point(50, 1)
        expected = self.R(target, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveOntoLongerLine(self):
        set_text(self.view, 'foo\nfoo bar\nfoo bar')
        add_selection(self.view, a=1, b=1)

        self.view.run_command('_vi_j_motion', {'mode': MODE_NORMAL, 'count': 1, 'xpos': 1})

        target = self.view.text_point(1, 1)
        expected = self.R(target, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveOntoShorterLine(self):
        set_text(self.view, 'foo bar\nfoo\nbar')
        add_selection(self.view, a=5, b=5)

        self.view.run_command('_vi_j_motion', {'mode': MODE_NORMAL, 'count': 1, 'xpos': 5})

        target = self.view.text_point(1, 0)
        target = self.view.line(target).b - 1
        expected = self.R(target, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveFromEmptyLine(self):
        set_text(self.view, '\nfoo\nbar')
        add_selection(self.view, a=0, b=0)

        self.view.run_command('_vi_j_motion', {'mode': MODE_NORMAL, 'count': 1, 'xpos': 0})

        target = self.view.text_point(1, 0)
        expected = self.R(target, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveFromEmptyLineToEmptyLine(self):
        set_text(self.view, '\n\nbar')
        add_selection(self.view, a=0, b=0)

        self.view.run_command('_vi_j_motion', {'mode': MODE_NORMAL, 'count': 1, 'xpos': 0})

        target = self.view.text_point(1, 0)
        expected = self.R(target, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveTooFar(self):
        set_text(self.view, 'foo\nbar\nbaz')
        add_selection(self.view, a=1, b=1)

        self.view.run_command('_vi_j_motion', {'mode': MODE_NORMAL, 'count': 10000, 'xpos': 1})

        target = self.view.text_point(2, 1)
        expected = self.R(target, target)

        self.assertEqual(expected, first_sel(self.view))


class Test_vi_j_InVisualMode(BufferTest):
    def testMoveOne(self):
        set_text(self.view, 'abc\nabc\nabc')
        add_selection(self.view, a=1, b=2)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL, 'count': 1, 'xpos': 1})

        target = self.view.text_point(1, 2)
        expected = self.R(1, target)

        self.assertEqual(expected, first_sel(self.view))

    # TODO: Fix this nonsense.
    def testMoveOneReversedNoCrossOver(self):
        set_text(self.view, 'abc\nabc\nabc')
        add_selection(self.view, a=2, b=0)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL, 'count': 1, 'xpos': 1})

        target = self.view.text_point(1, 2)
        expected = self.R(10, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveMany(self):
        set_text(self.view, ''.join(('abc\n',) * 60))
        add_selection(self.view, a=1, b=2)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL, 'count': 50, 'xpos': 1})

        target = self.view.text_point(50, 2)
        expected = self.R(1, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveOntoLongerLine(self):
        set_text(self.view, 'foo\nfoo bar\nfoo bar')
        add_selection(self.view, a=1, b=2)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL, 'count': 1, 'xpos': 1})

        target = self.view.text_point(1, 2)
        expected = self.R(1, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveOntoShorterLine(self):
        set_text(self.view, 'foo bar\nfoo\nbar')
        add_selection(self.view, a=5, b=6)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL, 'count': 1, 'xpos': 5})

        target = self.view.text_point(1, 0)
        target = self.view.full_line(target).b
        expected = self.R(5, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveFromEmptyLine(self):
        set_text(self.view, '\nfoo\nbar')
        add_selection(self.view, a=0, b=1)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL, 'count': 1, 'xpos': 0})

        target = self.view.text_point(1, 1)
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveFromEmptyLineToEmptyLine(self):
        set_text(self.view, '\n\nbar')
        add_selection(self.view, a=0, b=1)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL, 'count': 1, 'xpos': 0})

        target = self.view.text_point(1, 1)
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveTooFar(self):
        set_text(self.view, 'foo\nbar\nbaz')
        add_selection(self.view, a=1, b=2)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL, 'count': 10000, 'xpos': 1})

        target = self.view.text_point(2, 2)
        expected = self.R(1, target)

        self.assertEqual(expected, first_sel(self.view))


# TODO: Ensure that we only create empty selections while testing. Add assert_all_sels_empty()?
class Test_vi_j_InInternalNormalMode(BufferTest):
    def testMoveOne(self):
        set_text(self.view, 'abc\nabc\nabc')
        add_selection(self.view, a=1, b=1)

        self.view.run_command('_vi_j_motion', {'mode': _MODE_INTERNAL_NORMAL, 'count': 1, 'xpos': 1})

        target = self.view.text_point(1, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveMany(self):
        set_text(self.view, ''.join(('abc\n',) * 60))
        add_selection(self.view, a=1, b=1)

        self.view.run_command('_vi_j_motion', {'mode': _MODE_INTERNAL_NORMAL, 'count': 50, 'xpos': 1})

        target = self.view.text_point(50, 2)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveOntoLongerLine(self):
        set_text(self.view, 'foo\nfoo bar\nfoo bar')
        add_selection(self.view, a=1, b=1)

        self.view.run_command('_vi_j_motion', {'mode': _MODE_INTERNAL_NORMAL, 'count': 1, 'xpos': 1})

        target = self.view.text_point(1, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveOntoShorterLine(self):
        set_text(self.view, 'foo bar\nfoo\nbar')
        add_selection(self.view, a=5, b=5)

        self.view.run_command('_vi_j_motion', {'mode': _MODE_INTERNAL_NORMAL, 'count': 1, 'xpos': 5})

        target = self.view.text_point(1, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveFromEmptyLine(self):
        set_text(self.view, '\nfoo\nbar')
        add_selection(self.view, a=0, b=0)

        self.view.run_command('_vi_j_motion', {'mode': _MODE_INTERNAL_NORMAL, 'count': 1, 'xpos': 0})

        target = self.view.text_point(1, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveFromEmptyLineToEmptyLine(self):
        set_text(self.view, '\n\nbar')
        add_selection(self.view, a=0, b=0)

        self.view.run_command('_vi_j_motion', {'mode': _MODE_INTERNAL_NORMAL, 'count': 1, 'xpos': 0})

        target = self.view.text_point(1, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveTooFar(self):
        set_text(self.view, 'foo\nbar\nbaz')
        add_selection(self.view, a=1, b=1)

        self.view.run_command('_vi_j_motion', {'mode': _MODE_INTERNAL_NORMAL, 'count': 10000, 'xpos': 1})

        target = self.view.text_point(2, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))


class Test_vi_j_InVisualLineMode(BufferTest):
    def testMoveOne(self):
        set_text(self.view, 'abc\nabc\nabc')
        add_selection(self.view, a=0, b=4)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL_LINE, 'count': 1, 'xpos': 1})

        target = self.view.text_point(1, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveMany(self):
        set_text(self.view, ''.join(('abc\n',) * 60))
        add_selection(self.view, a=0, b=4)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL_LINE, 'count': 50, 'xpos': 1})

        target = self.view.text_point(50, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveFromEmptyLine(self):
        set_text(self.view, '\nfoo\nbar')
        add_selection(self.view, a=0, b=1)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL_LINE, 'count': 1, 'xpos': 0})

        target = self.view.text_point(1, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveFromEmptyLineToEmptyLine(self):
        set_text(self.view, '\n\nbar')
        add_selection(self.view, a=0, b=1)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL_LINE, 'count': 1, 'xpos': 0})

        target = self.view.text_point(1, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))

    def testMoveTooFar(self):
        set_text(self.view, 'foo\nbar\nbaz')
        add_selection(self.view, a=0, b=4)

        self.view.run_command('_vi_j_motion', {'mode': MODE_VISUAL_LINE, 'count': 10000, 'xpos': 1})

        target = self.view.text_point(2, 0)
        target = self.view.full_line(target).b
        expected = self.R(0, target)

        self.assertEqual(expected, first_sel(self.view))
