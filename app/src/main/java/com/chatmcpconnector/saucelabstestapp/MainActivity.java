package com.chatmcpconnector.saucelabstestapp;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.text.TextUtils;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Switch;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private static final String STATE_COUNTER = "counter";

    private final CounterModel counterModel = new CounterModel();
    private TextView counterValue;
    private TextView statusText;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        EditText nameInput = findViewById(R.id.nameInput);
        Button greetButton = findViewById(R.id.greetButton);
        TextView greetingResult = findViewById(R.id.greetingResult);
        Button decrementButton = findViewById(R.id.decrementButton);
        Button incrementButton = findViewById(R.id.incrementButton);
        Button resetButton = findViewById(R.id.resetButton);
        Switch testModeSwitch = findViewById(R.id.testModeSwitch);
        Button completeTestButton = findViewById(R.id.completeTestButton);

        counterValue = findViewById(R.id.counterValue);
        statusText = findViewById(R.id.statusText);

        if (savedInstanceState != null) {
            counterModel.restore(savedInstanceState.getInt(STATE_COUNTER, 0));
        }
        renderCounter();

        greetButton.setOnClickListener(view -> {
            String name = nameInput.getText().toString().trim();
            if (TextUtils.isEmpty(name)) {
                name = getString(R.string.default_tester_name);
            }
            greetingResult.setText(getString(R.string.greeting_result, name));
            greetingResult.setContentDescription(getString(R.string.greeting_result_description, name));
        });

        decrementButton.setOnClickListener(view -> {
            counterModel.decrement();
            renderCounter();
        });

        incrementButton.setOnClickListener(view -> {
            counterModel.increment();
            renderCounter();
        });

        resetButton.setOnClickListener(view -> {
            counterModel.reset();
            renderCounter();
        });

        testModeSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            statusText.setText(isChecked ? R.string.test_mode_enabled : R.string.ready_status);
            statusText.setTextColor(Color.parseColor(isChecked ? "#0B6E4F" : "#374151"));
        });

        completeTestButton.setOnClickListener(view -> {
            statusText.setText(R.string.test_successful);
            statusText.setTextColor(Color.parseColor("#0B6E4F"));
            statusText.setContentDescription(getString(R.string.test_successful_description));
        });
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        outState.putInt(STATE_COUNTER, counterModel.getValue());
        super.onSaveInstanceState(outState);
    }

    private void renderCounter() {
        counterValue.setText(String.valueOf(counterModel.getValue()));
        counterValue.setContentDescription(
            getString(R.string.counter_value_description, counterModel.getValue())
        );
    }
}
