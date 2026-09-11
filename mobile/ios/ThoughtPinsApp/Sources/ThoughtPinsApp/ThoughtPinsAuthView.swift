import Foundation
import AuthenticationServices
import AVFoundation
import SwiftUI
import ThoughtPinsCore
import UIKit
import UniformTypeIdentifiers

struct ThoughtPinsAuthView: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var creatingAccount = false
    @State private var usePhone = false
    @State private var identifier = ""
    @State private var password = ""
    @State private var phone = ""
    @State private var legalAccepted = false
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.openURL) private var openURL

    /// Whether a provider can actually produce a button.
    ///
    /// These gate the section header as well as the rows inside it. The header
    /// used to be gated on the server flags alone while the Google row also
    /// required `supportsOAuth`, so a build without a Google client ID drew an
    /// "Other ways to sign in" header over an empty section. That is the
    /// current production shape: client-config reports google enabled and apple
    /// disabled, and GIDClientID is empty in any build that has not had the
    /// client IDs injected.
    private var appleSignInAvailable: Bool {
        model.config?.oauthAppleEnabled == true
    }

    /// Google is only offered when Sign in with Apple is offered alongside it.
    ///
    /// Guideline 4.8 requires that an app using a third-party login service
    /// also offer an equivalent option that limits collection to name and
    /// email **and lets the person keep their email address private**. Our
    /// email-and-password sign-up does not meet the second half of that: it
    /// needs a real, working address. Sign in with Apple is the option that
    /// does, so Google without Apple is a 4.8 rejection waiting to happen.
    ///
    /// Deciding it here rather than in server config means no flag flipped
    /// during the review window can put the binary out of compliance. To offer
    /// Google, configure Apple sign-in and turn `oauth_apple_enabled` on; the
    /// two then appear together. Email and password are unaffected either way.
    private var googleSignInAvailable: Bool {
        model.config?.oauthGoogleEnabled == true
            && model.supportsOAuth(.google)
            && appleSignInAvailable
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    HStack(spacing: 10) {
                        ThoughtPinsBrandMark().frame(width: 32, height: 32)
                        Text("Thought Pins").font(.headline)
                    }
                    .padding(.top, 12)
                    VStack(alignment: .leading, spacing: 14) {
                        ThoughtPinsOrbit(size: 72)
                        Text(creatingAccount ? "Your life.\nA little more connected." : "Welcome back.")
                            .font(.system(.largeTitle, design: .default).weight(.bold)).tracking(-0.8)
                            .foregroundStyle(ThoughtPinsTheme.ink)
                            .accessibilityAddTraits(.isHeader)
                        Text("A private place for the people, moments, and ideas that matter to you.")
                            .font(.subheadline).lineSpacing(3).foregroundStyle(ThoughtPinsTheme.inkSoft)
                    }
                    Picker("Account action", selection: $creatingAccount) {
                        Text("Sign in").tag(false)
                        Text("Create account").tag(true)
                    }
                    .pickerStyle(.segmented)
                    VStack(alignment: .leading, spacing: 20) {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(usePhone ? "Phone" : "Email").font(.subheadline.weight(.medium))
                                Spacer()
                                Button(usePhone ? "Use email" : "Use phone") {
                                    usePhone.toggle()
                                    identifier = ""
                                    phone = ""
                                }
                                .font(.caption.weight(.medium)).frame(minHeight: 44)
                            }
                            if usePhone {
                                TextField("Phone", text: $phone)
                                    .textContentType(.telephoneNumber).keyboardType(.phonePad)
                                    .padding(15).background(ThoughtPinsTheme.canvas, in: RoundedRectangle(cornerRadius: 14))
                            } else {
                                TextField("Email", text: $identifier)
                                    .textContentType(.emailAddress).keyboardType(.emailAddress)
                                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                                    .padding(15).background(ThoughtPinsTheme.canvas, in: RoundedRectangle(cornerRadius: 14))
                            }
                        }
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Password").font(.subheadline.weight(.medium))
                            SecureField("Password", text: $password)
                                .textContentType(creatingAccount ? .newPassword : .password)
                                .submitLabel(.go)
                                .padding(15).background(ThoughtPinsTheme.canvas, in: RoundedRectangle(cornerRadius: 14))
                                .onSubmit(authenticate)
                        }
                        if creatingAccount {
                            Toggle("I consent to private AI processing of content I choose to send.", isOn: $legalAccepted)
                                .font(.footnote).tint(ThoughtPinsTheme.action)
                            legalLinks
                        }
                        Button(action: authenticate) {
                            HStack {
                                if model.authBusy { ProgressView().tint(.white) }
                                Text(creatingAccount ? "Create account" : "Sign in")
                                if !model.authBusy { Image(systemName: "arrow.right") }
                            }
                        }
                        .buttonStyle(ThoughtPinsPrimaryStyle())
                        .disabled(model.authBusy || (creatingAccount ? registrationBlocker : signInBlocker) != nil)
                        if let blocker = creatingAccount ? registrationBlocker : signInBlocker, !model.authBusy {
                            Text(blocker).font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if model.authBusy {
                            Text(creatingAccount ? "Creating account…" : "Signing in…")
                                .font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                                .accessibilityIdentifier("thoughtpins-auth-progress")
                        }
                        if !creatingAccount {
                            Button("Forgot password?") {
                                if let url = forgotPasswordMailURL() { openURL(url) }
                            }
                            .font(.footnote).frame(minHeight: 44)
                            .disabled(model.authBusy)
                            .accessibilityIdentifier("thoughtpins-forgot-password")
                        }
                        if appleSignInAvailable || googleSignInAvailable {
                            Divider()
                            if appleSignInAvailable {
                                SignInWithAppleButton(.signIn) { request in
                                    model.configureAppleSignInRequest(request)
                                } onCompletion: { result in
                                    Task { await model.completeAppleSignIn(result) }
                                }
                                .signInWithAppleButtonStyle(colorScheme == .dark ? .white : .black)
                                .frame(height: 50).disabled(model.authBusy)
                            }
                            if googleSignInAvailable {
                                Button(ThoughtPinsOAuthProvider.google.label) {
                                    Task { await model.oauthLogin(provider: .google) }
                                }
                                .frame(maxWidth: .infinity, minHeight: 50).disabled(model.authBusy)
                            }
                        }
                    }
                    .thoughtPinsCard(padding: 20)
                    if !creatingAccount { legalLinks }
                    Label("Your memories. Your control.", systemImage: "lock.shield")
                        .font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                        .frame(maxWidth: .infinity)
                }
                .padding(24).padding(.bottom, 16)
                .frame(maxWidth: 540).frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            .thoughtPinsScreen()
            .toolbar(.hidden, for: .navigationBar)
            .tint(ThoughtPinsTheme.action)
        }
    }

    private var legalLinks: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 20) { links }
            VStack(alignment: .leading, spacing: 4) { links }
        }
        .font(.caption).frame(maxWidth: .infinity)
    }

    @ViewBuilder private var links: some View {
        Link("Privacy", destination: model.legalURL(configured: model.config?.privacyPolicyUrl, fallbackPath: "/privacy")).frame(minHeight: 44)
        Link("Terms", destination: model.legalURL(configured: model.config?.termsUrl, fallbackPath: "/terms")).frame(minHeight: 44)
        Link("AI Disclosure", destination: model.legalURL(configured: model.config?.aiDisclosureUrl, fallbackPath: "/ai-disclosure")).frame(minHeight: 44)
    }

    private func authenticate() {
        guard !model.authBusy else { return }
        if creatingAccount {
            guard registrationBlocker == nil else { return }
            Task { await model.register(email: identifier.isEmpty ? nil : identifier, phone: phone.isEmpty ? nil : phone,
                                        password: password, consentToAIProcessing: legalAccepted) }
        } else {
            guard signInBlocker == nil else { return }
            Task { await model.login(identifier: identifier.isEmpty ? phone : identifier, password: password) }
        }
    }

    /// A pre-filled support email for password recovery. Carries the account
    /// identifier so support can locate the account, and deliberately nothing
    /// secret — no password, ever.
    private func forgotPasswordMailURL() -> URL? {
        let account = identifier.isEmpty ? phone : identifier
        let subject = "Thought Pins password help"
        let body = """
            I cannot sign in and would like to reset my password.

            Account email or phone: \(account.isEmpty ? "(fill this in)" : account)

            Please do not include my password in any reply.
            """
        var components = URLComponents()
        components.scheme = "mailto"
        components.path = "support@thoughtpins.com"
        components.queryItems = [
            URLQueryItem(name: "subject", value: subject),
            URLQueryItem(name: "body", value: body),
        ]
        return components.url
    }

    /// Why Sign in is disabled, or nil when it is not.
    ///
    /// Create account has had this guard from the start; Sign in did not, so an
    /// empty form still posted to `/v1/auth/login`. `LoginRequest` requires a
    /// password of at least one character, so that round trip could only ever
    /// fail — and it failed by putting the validator's own words, "Request
    /// validation failed", in front of the person's very first interaction with
    /// the app. Seen on a device on 2026-09-04, on the screen every App Review
    /// begins on.
    private var signInBlocker: String? {
        if identifier.isEmpty && phone.isEmpty {
            return "Enter the email address or phone number for your account."
        }
        if password.isEmpty {
            return "Enter your password."
        }
        return nil
    }

    /// Why Create account is disabled, or nil when it is not.
    ///
    /// A disabled button with no stated reason is the shape of a failed App
    /// Review: the reviewer cannot register, and nothing on screen says which
    /// of three rules they have not met yet.
    private var registrationBlocker: String? {
        if identifier.isEmpty && phone.isEmpty {
            return "Add an email address or phone number to create an account."
        }
        // Code points, matching the server's own length rule, so the client
        // never accepts a password the API is about to reject.
        let length = password.unicodeScalars.count
        if length < 12 {
            return "Choose a password of at least 12 characters."
        }
        if length > 256 {
            return "Choose a password of 256 characters or fewer."
        }
        if !legalAccepted {
            return "Accept AI processing above to create an account."
        }
        return nil
    }
}
