import os
import unittest
import numpy as np
from imp import reload
from mmdnn.conversion.examples.imagenet_test import TestKit
from mmdnn.conversion.examples.keras.extractor import keras_extractor
from mmdnn.conversion.keras.keras2_parser import Keras2Parser
from mmdnn.conversion.cntk.cntk_emitter import CntkEmitter

def _compute_SNR(x,y):
    noise = x - y
    noise_var = np.sum(noise ** 2)/len(noise) + 1e-7
    signal_energy = np.sum(y ** 2)/len(y)
    max_signal_energy = np.amax(y ** 2)
    SNR = 10 * np.log10(signal_energy/noise_var)
    PSNR = 10 * np.log10(max_signal_energy/noise_var)
    return SNR, PSNR


def _compute_max_relative_error(x,y):
    rerror = 0
    index = 0
    for i in range(len(x)):
        den = max(1.0, np.abs(x[i]), np.abs(y[i]))
        if np.abs(x[i]/den - y[i]/den) > rerror:
            rerror = np.abs(x[i]/den - y[i]/den)
            index = i
    return rerror, index


class CorrectnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        """ Set up the unit test by loading common utilities.
        """
        self.err_thresh = 0.0015
        self.snr_thresh = 12
        self.psnr_thresh = 30

    def _compare_outputs(self, original_predict, converted_predict):
        self.assertEquals(len(original_predict), len(converted_predict))
        error, ind = _compute_max_relative_error(converted_predict, original_predict)
        SNR, PSNR = _compute_SNR(converted_predict, original_predict)
        print("error:", error)
        print("SNR:", SNR)
        print("PSNR:", PSNR)
        self.assertGreater(SNR, self.snr_thresh)
        self.assertGreater(PSNR, self.psnr_thresh)
        self.assertLess(error, self.err_thresh)


class TestModels(CorrectnessTest):

    image_path = "mmdnn/conversion/examples/data/seagull.jpg"
    cachedir = "tests/cache/"
    tmpdir = "tests/tmp/"

    @staticmethod
    def KerasParse(architecture_name, image_path):
        # get original model prediction result
        original_predict = keras_extractor.inference(architecture_name, image_path)

        # download model
        model_filename = keras_extractor.download(architecture_name, TestModels.cachedir)

        # original to IR
        parser = Keras2Parser(model_filename)
        parser.gen_IR()
        parser.save_to_proto(TestModels.tmpdir + architecture_name + "_converted.pb")
        parser.save_weights(TestModels.tmpdir + architecture_name + "_converted.npy")
        del parser
        return original_predict


    @staticmethod
    def CntkEmit(original_framework, architecture_name, architecture_path, weight_path, image_path):
        print("Testing {} from {} to CNTK.".format(architecture_name, original_framework))

        # IR to code
        emitter = CntkEmitter((architecture_path, weight_path))
        emitter.run("converted_model.py", None, 'test')
        del emitter

        # import converted model
        import converted_model
        reload (converted_model)
        model_converted = converted_model.KitModel(TestModels.tmpdir + architecture_name + "_converted.npy")

        func = TestKit.preprocess_func[original_framework][architecture_name]
        img = func(image_path)
        predict = model_converted.eval({model_converted.arguments[0]:[img]})
        converted_predict = np.squeeze(predict)
        del model_converted
        del converted_model
        os.remove("converted_model.py")
        return converted_predict


    test_table = {
        'keras': {
            'vgg16'        : [CntkEmit],
            'vgg19'        : [CntkEmit],
            'inception_v3' : [CntkEmit],
            'resnet50'     : [CntkEmit],
            'densenet'     : [CntkEmit],
            'xception'     : [],
            # 'nasnet'       : [],
        }
    }

    def test_keras(self):
        # keras original
        original_framework = 'keras'

        for network_name in self.test_table[original_framework].keys():
            print("Testing {} model {} start.".format(original_framework, network_name))

            # get original model prediction result
            original_predict = self.KerasParse(network_name, self.image_path)

            for emit in self.test_table[original_framework][network_name]:
                converted_predict = emit.__func__(
                    original_framework,
                    network_name,
                    self.tmpdir + network_name + "_converted.pb",
                    self.tmpdir + network_name + "_converted.npy",
                    self.image_path)

                self._compare_outputs(original_predict, converted_predict)


            os.remove(self.tmpdir + network_name + "_converted.pb")
            os.remove(self.tmpdir + network_name + "_converted.npy")
            print("Testing {} model {} passed.".format(original_framework, network_name))

        print("Testing {} model all passed.".format(original_framework))
