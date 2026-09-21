import MIPStarRE.QPBT.Test.Soundness
import MIPStarRE.QPBT.Test.QubitForm
import MIPStarRE.QPBT.Test.Completeness
import MIPStarRE.QPBT.Test.LowDegreeGameTheorems

/-!
# Solution

The MIPStarRE-A library itself proves the four registered QPBT headline
theorems.
`Challenge.lean` re-declares the statements' definitional closure verbatim
under the same fully-qualified names, so importing the library is the entire
solution; comparator checks that the two environments declare identical
statements.
-/
