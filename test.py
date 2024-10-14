import pytest
from unittest.mock import patch
from script import isTrue, main  

def test_isTrue():
    assert isTrue() == "Hello World"

@patch('builtins.input', side_effect=['T'])
def test_main_with_T(mock_input):
    assert main() == "Hello World"

@patch('builtins.input', side_effect=['F'])
def test_main_with_F(mock_input):
    assert main() == "Not T"

@patch('builtins.input', side_effect=['A'])  # Any input other than T or F
def test_main_with_other_input(mock_input):
    assert main() == "Not T"

