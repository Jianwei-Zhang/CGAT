"""Shared public options for the single-gap and whole-genome gap-filling CLIs."""
import argparse

ROUNDS = 'MaximumExtensionRound'
LENGTH = 'MaximumExtensionLength'
DEFAULT_ROUNDS = 10
DEFAULT_LENGTH = 500_000


def extension_limit(value):
    if value == 'unlimited':
        return None
    try:
        number = int(value)
    except ValueError:
        number = -1
    if number < 0:
        raise argparse.ArgumentTypeError('expected a nonnegative integer or unlimited')
    return number


def add_options(limits, filtering, *, gapfill=None):
    """gapfill=None defers defaults until DEGAP.py has resolved its mode."""
    limits.add_argument('--' + ROUNDS, type=extension_limit, metavar='N|unlimited',
                        default=argparse.SUPPRESS,
                        help='Shared left/right attempts per gap, including unsuccessful attempts (GapFiller default: 10)')
    limits.add_argument('--' + LENGTH, type=extension_limit, metavar='BP|unlimited',
                        default=argparse.SUPPRESS,
                        help='Shared cumulative extension budget in bp; last completed attempt may cross it (GapFiller default: 500000)')
    switches = filtering.add_mutually_exclusive_group()
    switches.add_argument('--kmer_filter', action='store_true', default=argparse.SUPPRESS,
                          help='Filter candidate reads by k-mers (on by default in GapFiller)')
    switches.add_argument('--no-kmer-filter', dest='kmer_filter', action='store_false', default=argparse.SUPPRESS,
                          help='Disable candidate-read k-mer filtering')
    if gapfill is not None:
        filtering.set_defaults(**defaults(gapfill))


def defaults(gapfill):
    return {ROUNDS: DEFAULT_ROUNDS if gapfill else None,
            LENGTH: DEFAULT_LENGTH if gapfill else None, 'kmer_filter': gapfill}


def resolve_defaults(args, *, gapfill):
    for key, value in defaults(gapfill).items():
        vars(args).setdefault(key, value)


def format_options(params):
    """Forward zero, unlimited and false as distinct values, never by truthiness."""
    options = []
    for key in (ROUNDS, LENGTH):
        if key in params:
            value = params[key]
            options.append(('--' + key, 'unlimited' if value is None else str(value)))
    if 'kmer_filter' in params:
        options.append(('--kmer_filter' if params['kmer_filter'] else '--no-kmer-filter',))
    return options
