import re
import logging

import sublime
import sublime_plugin

from Vintageous import local_logger
from Vintageous.vi import actions
from Vintageous.vi import inputs
from Vintageous.vi import motions
from Vintageous.vi import utils
from Vintageous.vi.keys import cmd_types
from Vintageous.vi.keys import cmds
from Vintageous.vi.contexts import KeyContext
from Vintageous.vi.dot_file import DotFile
from Vintageous.vi.keys import mappings
from Vintageous.vi.keys import parse_sequence
from Vintageous.vi.keys import seq_to_command
from Vintageous.vi.keys import user_mappings
from Vintageous.vi.marks import Marks
from Vintageous.vi.registers import Registers
from Vintageous.vi.settings import SettingsManager
from Vintageous.vi.utils import directions
from Vintageous.vi.utils import get_logger
from Vintageous.vi.utils import input_types
from Vintageous.vi.utils import is_view
from Vintageous.vi.utils import jump_directions
from Vintageous.vi.utils import modes


# ============================================================================
# examples that need to work
#
#   ysta" => ys + t + [a as input for t] + [" as input for ys]
#   d/foobar<cr>gUw
#   ft:s/this/that/g<cr>gg
# ============================================================================


_logger = local_logger(__name__)


def _init_vintageous(view, new_session=False):
    """
    Initializes global data. Runs at startup and every time a view gets
    activated, loaded, etc.

    @new_session
      Whether we're starting up Sublime Text. If so, volatile data must be
      wiped.
    """

    if not is_view(view):
        # XXX: This seems to be necessary here.
        # Abort if we got a widget, panel...
        view.settings().set('command_mode', False)
        view.settings().set('inverse_caret_state', False)
        return

    state = State(view)

    if not state.reset_during_init:
        # Probably exiting from an input panel, like when using '/'. Don't
        # reset the global state, as it may contain data needed to complete
        # the command that's being built.
        state.reset_during_init = True
        return

    # Non-standard user setting.
    reset = state.settings.view['vintageous_reset_mode_when_switching_tabs']
    # XXX: If the view was already in normal mode, we still need to run the
    # init code. I believe this is due to Sublime Text (intentionally) not
    # serializing the inverted caret state and the command_mode setting when
    # first loading a file.
    if not reset and (state.mode != modes.NORMAL):
        return

    state.logger.info('[_init_vintageous] running init')

    if state.mode in (modes.VISUAL, modes.VISUAL_LINE):
        # TODO: Don't we need to pass a mode here?
        view.window().run_command('_enter_normal_mode', {'from_init': True})

    elif state.mode in (modes.INSERT, modes.REPLACE):
        # TODO: Don't we need to pass a mode here?
        view.window().run_command('_enter_normal_mode', {'from_init': True})

    elif (view.has_non_empty_selection_region() and len(view.sel()) > 1 and
          state.mode != modes.VISUAL):
          # Runs, for example, when we've performed a search via ST3 search
          # panel and we've pressed 'Find All'. In this case, we want to
          # ensure a consistent state for multiple selections.
          # TODO: We could end up with multiple selections in other ways
          #       that bypass _init_vintageous.
            state.mode = modes.VISUAL

    else:
        # This may be run when we're coming from cmdline mode.
        pseudo_visual = view.has_non_empty_selection_region()
        mode = modes.VISUAL if pseudo_visual else modes.INSERT
        # TODO: Maybe the above should be handled by State?
        state.enter_normal_mode()
        view.window().run_command('_enter_normal_mode', {'mode': mode,
                                                         'from_init': True})

    state.reset_command_data()
    if new_session:
        state.reset_volatile_data()

        # Load settings.
        DotFile.from_user().run()


# TODO: Implement this
plugin_manager = None


# TODO: Test me.
def plugin_loaded():
    view = sublime.active_window().active_view()
    _init_vintageous(view, new_session=True)


class State(object):
    """
    Manages global state needed to build commands and control modes, etc.

    Usage:
      Before using it, always instantiate with the view commands are going to
      target. `State` uses view.settings() and window.settings() for data
      storage.
    """

    registers = Registers()
    marks = Marks()
    context = KeyContext()

    def __init__(self, view):
        self.view = view
        # We have multiple types of settings: vi-specific (settings.vi) and
        # regular ST view settings (settings.view) and window settings
        # (settings.window).
        # TODO: Make this a descriptor. Why isn't it?
        self.settings = SettingsManager(self.view)

    @property
    def glue_until_normal_mode(self):
        """
        Indicates that editing commands should be grouped together in a single
        undo step once the user requests `_enter_normal_mode`.

        This property is *VOLATILE*; it shouldn't be persisted between
        sessions.
        """
        # FIXME: What happens when we have an incomplete command and we switch
        #        views? We should clean up.
        # TODO: Make this a window setting.
        return self.settings.vi['_vintageous_glue_until_normal_mode'] or False

    @glue_until_normal_mode.setter
    def glue_until_normal_mode(self, value):
        self.settings.vi['_vintageous_glue_until_normal_mode'] = value

    @property
    def gluing_sequence(self):
        """
        Indicates whether `PressKeys` is running a command and is grouping all
        of the edits in one single undo step.

        This property is *VOLATILE*; it shouldn't be persisted between
        sessions.
        """
        # TODO: Store this as a window setting.
        return self.settings.vi['_vintageous_gluing_sequence'] or False

    @gluing_sequence.setter
    def gluing_sequence(self, value):
        self.settings.vi['_vintageous_gluing_sequence'] = value

    @property
    def non_interactive(self):
        # FIXME: This property seems to do the same as gluing_sequence.
        """
        Indicates whether `PressKeys` is running a command and no interactive
        prompts should be used (for example, by the '/' motion.)

        This property is *VOLATILE*; it shouldn't be persisted between
        sessions.
        """
        # TODO: Store this as a window setting.
        return self.settings.vi['_vintageous_non_interactive'] or False

    @non_interactive.setter
    def non_interactive(self, value):
        if not isinstance(value, bool):
            raise ValueError('expected bool')

        self.settings.vi['_vintageous_non_interactive'] = value

    @property
    def input_parsers(self):
        """
        Contains parsers for user input, like '/' or 'f' need.
        """
        # TODO: Rename to 'validators'?
        # TODO: Use window settings for storage?
        # TODO: Enable setting lists directly.
        return self.settings.vi['_vintageous_input_parsers'] or []

    @input_parsers.setter
    def input_parsers(self, value):
        self.settings.vi['_vintageous_input_parsers'] = value

    @property
    def last_character_search(self):
        """
        Last character used as input for 'f' or 't'.
        """
        return self.settings.window['_vintageous_last_character_search'] or ''

    @last_character_search.setter
    def last_character_search(self, value):
        self.settings.window['_vintageous_last_character_search'] = value

    @property
    def last_character_search_forward(self):
        """
        ',' and ';' change directions depending on whether 'f' or 't' was
        issued previously.

        Returns `True` if the previous character search command was 'f'.
        """
        return self.settings.window['_vintageous_last_character_search_forward'] or False

    @last_character_search_forward.setter
    def last_character_search_forward(self, value):
        # FIXME: It isn't working.
        self.settings.window['_vintageous_last_character_search_forward'] = value

    @property
    def capture_register(self):
        """
        Returns `True` if `State` is expecting a register name next.
        """
        return self.settings.vi['capture_register'] or False

    @capture_register.setter
    def capture_register(self, value):
        self.settings.vi['capture_register'] = value

    @property
    def last_buffer_search(self):
        """
        Returns the last string used by buffer search commands such as '/' and
        '?'.
        """
        return self.settings.window['_vintageous_last_buffer_search'] or ''

    @last_buffer_search.setter
    def last_buffer_search(self, value):
        self.settings.window['_vintageous_last_buffer_search'] = value

    @property
    def reset_during_init(self):
        # Some commands gather user input through input panels. An input panel
        # is just a view, so when it's closed, the previous view gets
        # activated and Vintageous init code runs. In this case, however, we
        # most likely want the global state to remain unchanged. This variable
        # helps to signal this.
        #
        # For an example, see the '_vi_slash' command.
        value = self.settings.window['_vintageous_reset_during_init']
        if not isinstance(value, bool):
            return True
        return value

    @reset_during_init.setter
    def reset_during_init(self, value):
        if not isinstance(value, bool):
            raise ValueError('expected a bool')

        self.settings.window['_vintageous_reset_during_init'] = value

    # This property isn't reset automatically. _enter_normal_mode mode must
    # take care of that so it can repeat the commands issues while in
    # insert mode.
    @property
    def normal_insert_count(self):
        """
        Count issued to 'i' or 'a', etc. These commands enter insert mode.
        If passed a count, they must repeat the commands issued while in
        insert mode.
        """
        return self.settings.vi['normal_insert_count'] or '1'

    @normal_insert_count.setter
    def normal_insert_count(self, value):
        self.settings.vi['normal_insert_count'] = value

    # TODO: Make these simple properties that access settings descriptors?
    @property
    def sequence(self):
        """
        Sequence of keys that build the command.
        """
        return self.settings.vi['sequence'] or ''

    @sequence.setter
    def sequence(self, value):
        self.settings.vi['sequence'] = value

    @property
    def partial_sequence(self):
        """
        Sometimes we need to store a partial sequence to obtain the commands'
        full name. Such is the case of `gD`, for example.
        """
        return self.settings.vi['partial_sequence'] or ''

    @partial_sequence.setter
    def partial_sequence(self, value):
        self.settings.vi['partial_sequence'] = value

    @property
    def mode(self):
        """
        Current mode. It isn't guaranteed that the underlying view's .sel()
        will be in a consistent state (for example, that it will at least
        have one non-empty region in visual mode.
        """
        return self.settings.vi['mode'] or modes.UNKNOWN

    @mode.setter
    def mode(self, value):
        self.settings.vi['mode'] = value

    @property
    def action(self):
        return self.settings.vi['action'] or None

    @action.setter
    def action(self, value):
        self.settings.vi['action'] = value

    @property
    def motion(self):
        return self.settings.vi['motion'] or None

    @motion.setter
    def motion(self, value):
        self.settings.vi['motion'] = value

    @property
    def motion_count(self):
        return self.settings.vi['motion_count'] or ''

    @motion_count.setter
    def motion_count(self, value):
        self.settings.vi['motion_count'] = value

    @property
    def action_count(self):
        return self.settings.vi['action_count'] or ''

    @action_count.setter
    def action_count(self, value):
        self.settings.vi['action_count'] = value

    @property
    def user_input(self):
        return self.settings.vi['user_input'] or ''

    @user_input.setter
    def user_input(self, value):
        self.settings.vi['user_input'] = value

    @property
    def repeat_data(self):
        """
        Stores (type, cmd_name_or_key_seq, , mode) so '.' can use them.

        `type` may be 'vi' or 'native'. `vi`-commands are executed VIA_PANEL
        `PressKeys`, while `native`-commands are executed via .run_command().
        """
        return self.settings.vi['repeat_data'] or None

    @repeat_data.setter
    def repeat_data(self, value):
        self.logger.info("setting repeat data {0}".format(value))
        self.settings.vi['repeat_data'] = value

    @property
    def last_macro(self):
        """
        Stores the last recorded macro.
        """
        return self.settings.window['_vintageous_last_macro'] or None

    @last_macro.setter
    def last_macro(self, value):
        """
        Stores the last recorded macro.
        """
        # FIXME: Check that we're storing a valid macro?
        self.settings.window['_vintageous_last_macro'] = value

    @property
    def recording_macro(self):
        return self.settings.window['_vintageous_recording_macro'] or False

    @recording_macro.setter
    def recording_macro(self, value):
        # FIXME: Check that we're storing a bool?
        self.settings.window['_vintageous_recording_macro'] = value

    @property
    def count(self):
        """
        Calculates the actual count for the current command.
        """
        c = 1
        if self.action_count and not self.action_count.isdigit():
            raise ValueError('action count must be a digit')

        if self.motion_count and not self.motion_count.isdigit():
            raise ValueError('motion count must be a digit')

        if self.action_count:
            c = int(self.action_count) or 1

        if self.motion_count:
            c *= (int(self.motion_count) or 1)

        if c < 1:
            raise ValueError('count must be greater than 0')

        return c

    @property
    def xpos(self):
        """
        Stores the current xpos for carets.
        """
        return self.settings.vi['xpos'] or 0

    @xpos.setter
    def xpos(self, value):
        if not isinstance(value, int):
            raise ValueError('xpos must be an int')

        self.settings.vi['xpos'] = value

    @property
    def visual_block_direction(self):
        """
        Stores the current visual block direction for the current selection.
        """
        return self.settings.vi['visual_block_direction'] or directions.DOWN

    @visual_block_direction.setter
    def visual_block_direction(self, value):
        if not isinstance(value, int):
            raise ValueError('visual_block_direction must be an int')

        self.settings.vi['visual_block_direction'] = value

    @property
    def logger(self):
        # FIXME: potentially very slow?
        # return get_logger()
        global _logger
        return _logger()

    @property
    def register(self):
        """
        Stores the current open register, as requested by the user.
        """
        # TODO: Maybe unify with Registers?
        # TODO: Validate register name?
        return self.settings.vi['register'] or '"'

    @register.setter
    def register(self, value):
        if len(str(value)) > 1:
            raise ValueError('register must be an character')

        self.logger.info('opening register {0}'.format(value))
        self.settings.vi['register'] = value
        self.capture_register = False

    def pop_parser(self):
        parsers = self.input_parsers
        current = parsers.pop()
        self.input_parsers = parsers
        return current

    def enter_normal_mode(self):
        self.mode = modes.NORMAL

    def enter_visual_mode(self):
        self.mode = modes.VISUAL

    def enter_visual_line_mode(self):
        self.mode = modes.VISUAL_LINE

    def enter_insert_mode(self):
        self.mode = modes.INSERT

    def enter_replace_mode(self):
        self.mode = modes.REPLACE

    def enter_select_mode(self):
        self.mode = modes.SELECT

    def enter_visual_block_mode(self):
        self.mode = modes.VISUAL_BLOCK

    def reset_sequence(self):
        self.sequence = ''
    def display_status(self):
        msg = "{0} {1}"
        mode_name = modes.to_friendly_name(self.mode)
        mode_name = '-- {0} --'.format(mode_name) if mode_name else ''
        sublime.status_message(msg.format(mode_name, self.sequence))

    def reset_partial_sequence(self):
        self.partial_sequence = ''
    def reset_user_input(self):
        self.input_parsers = []
        self.user_input = ''

    def reset_register_data(self):
        self.register = '"'
        self.capture_register = False

    def must_scroll_into_view(self):
        return (self.motion and self.motion.get('scroll_into_view'))

    def scroll_into_view(self):
        v = sublime.active_window().active_view()
        # Make sure we show the first caret on the screen, but don't show
        # its surroundings.
        v.show(v.sel()[0], False)

    def reset_command_data(self):
        # Resets all temporary data needed to build a command or partial
        # command to their default values.
        self.update_xpos()
        if self.must_scroll_into_view():
            self.scroll_into_view()
        self.action = None
        self.motion = None
        self.action_count = ''
        self.motion_count = ''

        self.reset_sequence()
        self.reset_partial_sequence()
        self.reset_user_input()
        self.reset_register_data()

    def update_xpos(self):
        if self.motion and self.motion.get('updates_xpos'):
            try:
                xpos = self.view.rowcol(self.view.sel()[0].b)[1]
            except Exception as e:
                print(e)
                raise ValueError('could not set xpos')

            self.xpos = xpos

    def reset(self):
        # TODO: Remove this when we've ported all commands. This is here for
        # retrocompatibility.
        self.reset_command_data()

    def reset_volatile_data(self):
        """
        Resets window- or application-wide data to their default values when
        starting a new Vintageous session.
        """
        self.glue_until_normal_mode = False
        self.view.run_command('unmark_undo_groups_for_gluing')
        self.gluing_sequence = False
        self.non_interactive = False
        self.reset_during_init = True

    def _set_parsers(self, command):
        """
        Returns `True` if we've had to run an immediate parser via an input
        panel.
        """
        if command.get('input'):

            # XXX: Special case. We should probably find a better solution.
            if self.recording_macro and (command['input'] == 'vi_q'):
                # We discard the parser, as we want to be able to press
                # 'q' to stop the macro recorder.
                return

            # Our command requests input from the user. Let's see how we
            # should go about it.
            parser_name = command['input']

            parser_list = self.input_parsers
            parser_list.append(parser_name)
            self.input_parsers = parser_list

            return self._run_parser_via_panel()

    def _run_parser_via_panel(self):
        """
        Returns `True` if the current parser needs to be run via a panel.

        If needed, it runs the input-panel-based parser.
        """
        if not self.input_parsers:
            return False

        parser_name = self.input_parsers[-1]
        parser, type_, post_parser = inputs.get(self, parser_name)

        if type_ == input_types.VIA_PANEL:
            # Let the input-collection command collect input.
            sublime.active_window().run_command(parser)
            return True

        return False

    def set_command(self, command):
        """
        Sets the current command to @command.

        @command
          A command definition as found in `keys.py`.
        """
        if command['type'] == cmd_types.MOTION:
            if self.runnable():
                # We already have a motion, so this looks like an error.
                raise ValueError('too many motions')

            self.motion = command
            if self.mode == modes.OPERATOR_PENDING:
                self.mode = modes.NORMAL

            if self._set_parsers(command):
                return

        elif command['type'] == cmd_types.ACTION:
            if self.runnable():
                # We already have an action, so this looks like an error.
                raise ValueError('too many actions')

            self.action = command

            if (self.action['motion_required'] and
                not self.in_any_visual_mode()):
                    self.mode = modes.OPERATOR_PENDING

            if self._set_parsers(command):
                return

        else:
            self.logger.info("[State] command: {0}".format(command))
            raise ValueError('unexpected command type')

    def in_any_visual_mode(self):
        return (self.mode in (modes.VISUAL,
                              modes.VISUAL_LINE,
                              modes.VISUAL_BLOCK))

    def can_run_action(self):
        if (self.action and
            (not self.action['motion_required'] or
             self.in_any_visual_mode())):
                return True

    def get_visual_repeat_data(self):
        """
        Returns the data needed to repeat a visual mode command in normal mode.
        """
        if self.mode != modes.VISUAL:
            return

        s0 = self.view.sel()[0]
        lines = self.view.rowcol(s0.end())[0] - self.view.rowcol(s0.begin())[0]
        if lines > 0:
            chars = self.view.rowcol(s0.end())[1]
        else:
            chars = s0.size()

        return (lines, chars)

    def runnable(self):
        """
        Returns `True` if we can run the state data as it is.
        """
        if self.input_parsers:
            return False

        if self.action and self.motion:
            if self.mode != modes.NORMAL:
                raise ValueError('wrong mode')
            return True

        if self.can_run_action():
            if self.mode == modes.OPERATOR_PENDING:
                raise ValueError('wrong mode')
            return True

        if self.motion:
            if self.mode == modes.OPERATOR_PENDING:
                raise ValueError('wrong mode')
            return True

        return False

    def eval(self):
        """
        Run data as a command if possible.
        """
        if self.runnable():
            action_func = motion_func = None
            action_cmd = motion_cmd = None

            if self.action:
                action_func = getattr(actions, self.action['name'], None)

                if action_func is None:
                    self.logger.info('[State] action not implemented: {0}'.format(self.action))
                    self.reset_command_data()
                    return

                action_cmd = action_func(self)
                self.logger.info('[State] action cmd data: {0}'.format(action_cmd))

            if self.motion:
                motion_func = getattr(motions, self.motion['name'], None)

                if motion_func is None:
                    self.logger.info('[State] motion not implemented: {0}'.format(self.motion))
                    self.reset_command_data()
                    return

                motion_cmd = motion_func(self)
                self.logger.info('[State] motion cmd data: {0}'.format(motion_cmd))

            if action_func and motion_func:
                self.logger.info('[State] full command, switching to internal normal mode')
                self.mode = modes.INTERNAL_NORMAL

                # TODO: Make a requirement that motions and actions take a
                # 'mode' param.
                if 'mode' in action_cmd['action_args']:
                    action_cmd['action_args']['mode'] = modes.INTERNAL_NORMAL

                if 'mode' in motion_cmd['motion_args']:
                    motion_cmd['motion_args']['mode'] = modes.INTERNAL_NORMAL

                args = action_cmd['action_args']
                args['count'] = 1
                # let the action run the motion within its edit object so that we don't need to
                # worry about grouping edits to the buffer.
                args['motion'] = motion_cmd
                self.logger.info('[Stage] motion in motion+action: {0}'.format(motion_cmd))

                if self.glue_until_normal_mode and not self.gluing_sequence:
                    # We need to tell Sublime Text now that it should group
                    # all the next edits until we enter normal mode again.
                    sublime.active_window().run_command('mark_undo_groups_for_gluing')

                sublime.active_window().run_command(action_cmd['action'], args)
                if not self.non_interactive:
                    if self.action['repeatable']:
                        self.repeat_data = ('vi', str(self.sequence), self.mode, None)
                self.reset_command_data()
                return

            if motion_func:
                self.logger.info('[State] lone motion cmd: {0}'.format(motion_cmd))

                sublime.active_window().run_command(
                                                motion_cmd['motion'],
                                                motion_cmd['motion_args'])

            if action_func:
                self.logger.info('[Stage] lone action cmd '.format(action_cmd))
                if self.mode == modes.NORMAL:
                    self.logger.info('[State] switching to internal normal mode')
                    self.mode = modes.INTERNAL_NORMAL

                    if 'mode' in action_cmd['action_args']:
                        action_cmd['action_args']['mode'] = modes.INTERNAL_NORMAL
                elif self.mode in (modes.VISUAL, modes.VISUAL_LINE):
                    self.view.add_regions('visual_sel', list(self.view.sel()))

                # Some commands, like 'i' or 'a', open a series of edits that
                # need to be grouped together unless we are gluing a larger
                # sequence through PressKeys. For example, aFOOBAR<Esc> should
                # be grouped atomically, but not inside a sequence like
                # iXXX<Esc>llaYYY<Esc>, where we want to group the whole
                # sequence instead.
                if self.glue_until_normal_mode and not self.gluing_sequence:
                    sublime.active_window().run_command('mark_undo_groups_for_gluing')

                seq = self.sequence
                visual_repeat_data = self.get_visual_repeat_data()
                action = self.action

                sublime.active_window().run_command(action_cmd['action'],
                                                action_cmd['action_args'])

                if not (self.gluing_sequence and self.glue_until_normal_mode):
                    if action['repeatable']:
                        self.repeat_data = ('vi', seq, self.mode, visual_repeat_data)


            self.logger.info('running command: action: {0} motion: {1}'.format(self.action,
                                                                          self.motion))

            if self.mode == modes.INTERNAL_NORMAL:
                self.enter_normal_mode()
            self.reset_command_data()


# TODO: Remove this when we've ported all commands.
VintageState = State
