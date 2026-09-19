import MIPStarRE.QPBT.Test.Soundness
import MIPStarRE.QPBT.Test.QubitForm

/-!
# Solution

The MIPStarRE-A library itself proves the challenge theorems
`MIPStarRE.QPBT.pauli_soundness` and `MIPStarRE.QPBT.pauli_soundness_qubit`.
`Challenge.lean` re-declares the statements' definitional closure verbatim
under the same fully-qualified names, so importing the library is the entire
solution; comparator checks that the two environments declare identical
statements.
-/
