package com.chatmcpconnector.saucelabstestapp;

import static androidx.test.espresso.Espresso.closeSoftKeyboard;
import static androidx.test.espresso.Espresso.onView;
import static androidx.test.espresso.action.ViewActions.click;
import static androidx.test.espresso.action.ViewActions.replaceText;
import static androidx.test.espresso.assertion.ViewAssertions.matches;
import static androidx.test.espresso.matcher.ViewMatchers.withId;
import static androidx.test.espresso.matcher.ViewMatchers.withText;

import androidx.test.ext.junit.rules.ActivityScenarioRule;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.filters.LargeTest;

import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
@LargeTest
public final class MainActivityTest {
    @Rule
    public ActivityScenarioRule<MainActivity> activityRule =
        new ActivityScenarioRule<>(MainActivity.class);

    @Test
    public void greetingCounterAndCompletionFlowWorks() {
        onView(withId(R.id.nameInput)).perform(replaceText("Sauce"));
        closeSoftKeyboard();
        onView(withId(R.id.greetButton)).perform(click());
        onView(withId(R.id.greetingResult)).check(matches(withText("Hallo, Sauce!")));

        onView(withId(R.id.incrementButton)).perform(click(), click());
        onView(withId(R.id.counterValue)).check(matches(withText("2")));

        onView(withId(R.id.resetButton)).perform(click());
        onView(withId(R.id.counterValue)).check(matches(withText("0")));

        onView(withId(R.id.completeTestButton)).perform(click());
        onView(withId(R.id.statusText)).check(matches(withText("STATUS: TEST ERFOLGREICH")));
    }
}
