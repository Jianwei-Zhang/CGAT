# Class for storing data about a matrix
package matrix;

use Query;

# Class inheritance
our @ISA = "Query";


use strict;

# Class attributes
my @Everyone;

# Constructor and initialization
sub new {
	my $class = shift;
	my $self = {@_};
	$self = $class->SUPER::new();
	return $self;
}

# Class accessor methods

# Utility methods that access data on matrix table

1;
