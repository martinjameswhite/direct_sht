#!/usr/bin/env python
#
# Code to deconvolve the mode-coupling of pseudo-Cls
# induced by a mask
#

import numpy  as np
import sys
from   scipy.interpolate import interp1d

sys.path.append('../sht')
from  threej000 import Wigner3j




class MaskDeconvolution:
    def __init__(self, lmax, W_l, verbose=True):
        """
        Class to deconvolve the mode-coupling of pseudo-Cls.

        It computes the necessary Wigner 3j symbols and mode-coupling matrix on
        initialization so that they do not have to be recomputed on successive calls
        to mode-decouple the pseudo-Cls of noise-debiased bandpowers.

        :param lmax: int. Maximum multipole to compute the mode-coupling matrix for.
        :param W_l: 1D numpy array. Window function. Must be provided at every ell.
                    If shorter than 2*lmax will be right-padded with zeros.
        :param verbose: bool. Whether to print out information about progress
        """
        self.lmax = lmax
        pad       = max(0,2*lmax+1-W_l.size)
        self.W_l  = np.pad(W_l,(0,pad),'constant',constant_values=0)
        # 
        # Precompute the expensive stuff
        if verbose:
            print("Precomputing Wigner 3j symbols...")
        # Precompute the required Wigner 3js
        self.w3j000 = Wigner3j(2 * lmax + 1)
        #
        if verbose:
            print("Computing the mode-coupling matrix...")
        # Compute the mode-coupling matrix
        self.Mll = self.get_M()
        #
    def __call__(self,C_l,lperBin):
        """
        Compute the noise-debiased and mode-decoupled bandpowers given some binning scheme.
        :param C_l: 1D numpy array of length self.lmax + 1.
                    Per-ell angular power spectrum of the signal.
        :param binning_matrix: An Nbin x Nell matrix to perform the binning.
        :return: tuple of (1D numpy array, 1D numpy array). The first array contains
                    the ells at which the bandpowers are computed. The second array
                    contains the noise-debiased and mode-decoupled bandpowers.
        """
        # We could alternatively pad this?
        assert (len(C_l) == self.lmax + 1), ("C_l must be provided up to the lmax"
                                             " with which the class was initialized")
        self.lperBin = lperBin
        # Bin the matrix
        self.init_binning()
        Mbb = self.bin_matrix(self.Mll)
        # Invert the binned matrix
        self.Mbb_inv = np.linalg.inv(Mbb)
        # Bin the Cls and Nls
        Cb = self.bin_Cls(C_l)
        # Mode-decouple the noise-debiased bandpowers
        Cb_decoupled = self.decouple_Cls(self.Mbb_inv,Cb)
        return( (self.binned_ells,Cb_decoupled) )
        #
    def W(self,l,debug=False):
        """
        Window function for a given multipole l.
        :param l: int. Multipole to evaluate the window function at.
        :param debug: Bool. If True, check the mode-coupling matrix becomes 1 in the full-sky.
        :return: float. Value of the window function at multipole l.
        """
        if debug:
            # In the full sky, the mode-coupling matrix should become the identity matrix
            if l == 0:
                return 4 * np.pi  # [\int d\hat{n} Y^*_{00}(\hat{n})]^2
            else:
                return 0
        else:
            return self.W_l[l]
        #
    def get_M(self,debug=False):
        """
        Compute the per-multipole mode-coupling matrix M_{l1,l2} for a given lmax.
        :param lmax: int. Maximum multipole to compute the mode-coupling matrix for.
        :param debug: Bool. If True, check the matrix becomes the identity in the full-sky limit.
        :return: 2D array of shape (lmax+1,lmax+1) containing the mode-coupling matrix.
        """
        M = np.zeros((self.lmax+1, self.lmax+1))
        for l1 in range(self.lmax+1):
            for l2 in range(self.lmax+1):
                for l3 in range(abs(l1-l2),l1+l2+1):
                    if (l1+l2+l3)%2==0:
                        M[l1,l2] += (2*l2+1)*(2*l3+1) *\
                                    self.w3j000(l1,l2,l3)**2 *\
                                    self.W(l3,debug)
        M /= 4*np.pi
        return(M)
        #
    def init_binning(self):
        """
        Set up the binning matrix to combine Cls and mode-coupling
        matrix into coarser ell bins.
        """
        self.bins = np.zeros(((self.lmax+1) // self.lperBin, self.lmax + 1))
        self.bins_no_weight = self.bins.copy()
        for i in range(0, self.lmax + 1, self.lperBin):
            self.bins[i // self.lperBin, i:i + self.lperBin] = 1 / float(self.lperBin)
            self.bins_no_weight[i // self.lperBin, i:i + self.lperBin] = 1
        # Also set it such that we drop the ell=0 bin
        # when we do our average(s).
        self.bins[0, 0] = 0.0
        self.bins_no_weight[0, 0] = 0.0
        self.binned_ells = np.dot(self.bins, np.arange(self.lmax+1))

    def binning_matrix(self,type='linear',step=16):
        """
        Returns a 'binning matrix', B, such that B.vec is a binned
        version of vec.
        :param type: Type of binning.
                     'linear' (default) gives linear binning.
        :param step: size of linear step.
        :return 2D array of shape (Nbins,lmax).
        """
        Nl   = self.lmax+1
        bins = np.zeros( (Nl,Nl) )
        if type=='linear':
            dell = lambda ell: step
        elif type=='sqrt':
            dell = lambda ell: int(np.ceil(np.sqrt(4.*ell)+step))
        else:
            raise RuntimeError("Unknown step type.")
        ii = 0
        l0 = 2 # Remove monopole and dipole.
        l1 = l0 + dell(l0)
        while l1<=Nl:
            bins[ii,l0:min(l1,Nl)] = 1/float(l1-l0)
            l0,l1 = l1,l1+dell(l1)
            ii   += 1
        bins = bins[:ii,:]
        return(bins)
        #
    def bin_matrix(self,M):
        """
        Bin the mode-coupling matrix into bandpowers
        :param M: 2D array of shape (lmax+1,lmax+1) containing
                  the mode-coupling matrix.
        :return: 2D array of shape (lmax+1//lperBin,lmax+1//lperBin)
                  containing the binned mode-coupling matrix
        """
        return np.matmul(np.matmul(self.bins, M), self.bins_no_weight.T)
        #
    def bin_Cls(self,Cl):
        """
        Bin the Cls into bandpowers
        :param Cl: 1D array of shape (lmax+1) containing the Cls
        :return: 1D array of shape (lmax+1//lperBin) containing the binned Cls
        """
        return np.dot(self.bins, Cl)
        #
    def decouple_Cls(self,Minv,Cb):
        """
        Noise-debias and bode-decouple some bandpowers
        :param Minv: 2D array of shape (lmax+1//lperBin,lmax+1//lperBin)
                     containing the inverse of the binned mode-coupling matrix
        :param Cb: 1D array of shape (lmax+1//lperBin) containing the binned Cls
        :return: 1D array of shape (lmax+1//lperBin) containing the
                    mode-decoupled bandpowers
        """
        return np.matmul(Cb,Minv)
        #
    def convolve_theory_Cls(self, Clt):
        """
        Convolve some theory Cls with the bandpower window function
        :param Clt: 1D numpy array of length self.lmax+1. Theory Cls
        :return: 1D numpy array of length (lmax+1//lperBin)
        """
        assert (self.Mbb_inv is not None), "Must call __call__ before convolving theory Cls"
        assert (len(Clt) == self.lmax + 1), ("Clt must be provided up to the lmax")
        return self.decouple_Cls(self.Mbb_inv, self.bin_Cls(np.dot(self.Mll, Clt)))

