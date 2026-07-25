package com.chatmcpconnector.saucelabstestapp;

public final class CounterModel {
    private int value;

    public int increment() {
        return ++value;
    }

    public int decrement() {
        if (value > 0) {
            value--;
        }
        return value;
    }

    public int reset() {
        value = 0;
        return value;
    }

    public int getValue() {
        return value;
    }

    public void restore(int restoredValue) {
        value = Math.max(0, restoredValue);
    }
}
