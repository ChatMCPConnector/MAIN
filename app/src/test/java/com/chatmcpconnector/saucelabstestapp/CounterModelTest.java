package com.chatmcpconnector.saucelabstestapp;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public final class CounterModelTest {
    @Test
    public void counterNeverDropsBelowZero() {
        CounterModel model = new CounterModel();

        assertEquals(0, model.decrement());
        assertEquals(1, model.increment());
        assertEquals(0, model.decrement());
        assertEquals(0, model.decrement());
    }

    @Test
    public void resetAndRestoreAreDeterministic() {
        CounterModel model = new CounterModel();

        model.increment();
        model.increment();
        assertEquals(0, model.reset());

        model.restore(7);
        assertEquals(7, model.getValue());

        model.restore(-4);
        assertEquals(0, model.getValue());
    }
}
